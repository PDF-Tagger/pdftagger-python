"""Unit tests for PdfTaggerClient with the HTTP layer mocked by respx."""

import httpx
import pytest
import respx

import pdftagger.client as client_module
from pdftagger import (
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InsufficientCreditsError,
    JobFailed,
    JobTimeout,
    NotFoundError,
    PdfTaggerClient,
    RateLimitError,
)

BASE = "https://api.pdf-tagger.com"


def make_client() -> PdfTaggerClient:
    return PdfTaggerClient(api_key="sk_live_test")


def err(status: int, type_: str = "some_error") -> httpx.Response:
    return httpx.Response(status, json={"error": {"type": type_, "message": f"boom {status}"}})


@respx.mock
def test_get_account_and_auth_header():
    route = respx.get(f"{BASE}/v1/me").mock(
        return_value=httpx.Response(200, json={"account_id": "acct_1", "credits_available": 42})
    )
    with make_client() as client:
        account = client.get_account()

    assert account.account_id == "acct_1"
    assert account.credits_available == 42
    assert route.calls.last.request.headers["authorization"] == "Bearer sk_live_test"
    assert route.calls.last.request.headers["user-agent"].startswith("pdftagger-python/")


@respx.mock
def test_create_upload():
    respx.post(f"{BASE}/v1/uploads").mock(
        return_value=httpx.Response(
            201,
            json={
                "upload_url": "https://s3.example.com/upload",
                "fields": {"key": "u/1.pdf", "x-amz-signature": "sig"},
                "key": "u/1.pdf",
            },
        )
    )
    with make_client() as client:
        upload = client.create_upload(filename="report.pdf")

    assert upload.key == "u/1.pdf"
    assert upload.fields["x-amz-signature"] == "sig"


@respx.mock
def test_upload_file_posts_fields_before_file(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")

    route = respx.post("https://s3.example.com/upload").mock(return_value=httpx.Response(204))

    with make_client() as client:
        from pdftagger.models import Upload

        upload = Upload(
            upload_url="https://s3.example.com/upload",
            fields={"key": "u/1.pdf", "policy": "p", "x-amz-signature": "sig"},
            key="u/1.pdf",
        )
        client.upload_file(upload, pdf)

    body = route.calls.last.request.content
    # Every presigned field is present...
    assert b'name="key"' in body
    assert b'name="policy"' in body
    assert b'name="file"' in body
    # ...and the file part comes last, as S3 requires.
    assert body.index(b'name="key"') < body.index(b'name="file"')
    assert body.index(b'name="policy"') < body.index(b'name="file"')


@respx.mock
def test_upload_file_raises_on_s3_error(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")
    respx.post("https://s3.example.com/upload").mock(return_value=httpx.Response(403))

    from pdftagger.models import Upload

    upload = Upload(upload_url="https://s3.example.com/upload", fields={"key": "u/1.pdf"}, key="u/1.pdf")
    with make_client() as client:
        with pytest.raises(APIError) as exc:
            client.upload_file(upload, pdf)
    assert exc.value.status_code == 403


@respx.mock
def test_submit_job_sends_options_and_idempotency():
    route = respx.post(f"{BASE}/v1/jobs").mock(
        return_value=httpx.Response(202, json={"id": "job_1", "status": "processing"})
    )
    with make_client() as client:
        job = client.submit_job(key="u/1.pdf", ocr=True, embed_fonts=True, idempotency_key="idem-1")

    assert job.id == "job_1"
    assert job.status == "processing"
    request = route.calls.last.request
    assert request.headers["idempotency-key"] == "idem-1"
    import json as _json

    sent = _json.loads(request.content)
    assert sent["key"] == "u/1.pdf"
    assert sent["options"] == {"ocr": True, "embed_fonts": True}


@respx.mock
def test_submit_job_omits_empty_options():
    route = respx.post(f"{BASE}/v1/jobs").mock(
        return_value=httpx.Response(202, json={"id": "job_1", "status": "processing"})
    )
    with make_client() as client:
        client.submit_job(key="u/1.pdf")

    import json as _json

    sent = _json.loads(route.calls.last.request.content)
    assert "options" not in sent
    assert "idempotency-key" not in route.calls.last.request.headers


@pytest.mark.parametrize(
    "status,expected",
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (402, InsufficientCreditsError),
        (404, NotFoundError),
        (409, ConflictError),
        (500, APIError),
    ],
)
@respx.mock
def test_error_status_maps_to_exception(status, expected):
    respx.get(f"{BASE}/v1/me").mock(return_value=err(status))
    with make_client() as client:
        with pytest.raises(expected) as exc:
            client.get_account()
    assert exc.value.status_code == status
    assert exc.value.type == "some_error"


@respx.mock
def test_rate_limit_carries_retry_after():
    respx.get(f"{BASE}/v1/me").mock(
        return_value=httpx.Response(
            429, headers={"Retry-After": "7"}, json={"error": {"type": "rate_limited", "message": "slow down"}}
        )
    )
    with make_client() as client:
        with pytest.raises(RateLimitError) as exc:
            client.get_account()
    assert exc.value.retry_after == 7


@respx.mock
def test_tag_pdf_full_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda *_: None)

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")

    respx.post(f"{BASE}/v1/uploads").mock(
        return_value=httpx.Response(
            201, json={"upload_url": "https://s3.example.com/upload", "fields": {"key": "u/1.pdf"}, "key": "u/1.pdf"}
        )
    )
    respx.post("https://s3.example.com/upload").mock(return_value=httpx.Response(204))
    respx.post(f"{BASE}/v1/jobs").mock(
        return_value=httpx.Response(202, json={"id": "job_1", "status": "processing"})
    )
    respx.get(f"{BASE}/v1/jobs/job_1").mock(
        side_effect=[
            httpx.Response(200, json={"id": "job_1", "status": "processing"}),
            httpx.Response(200, json={"id": "job_1", "status": "completed", "credits_used": 3}),
        ]
    )

    with make_client() as client:
        job = client.tag_pdf(pdf, ocr=True)

    assert job.succeeded
    assert job.credits_used == 3


@respx.mock
def test_tag_pdf_wait_false_returns_without_polling(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")

    respx.post(f"{BASE}/v1/uploads").mock(
        return_value=httpx.Response(
            201, json={"upload_url": "https://s3.example.com/upload", "fields": {"key": "u/1.pdf"}, "key": "u/1.pdf"}
        )
    )
    respx.post("https://s3.example.com/upload").mock(return_value=httpx.Response(204))
    respx.post(f"{BASE}/v1/jobs").mock(return_value=httpx.Response(202, json={"id": "job_1", "status": "processing"}))
    job_route = respx.get(f"{BASE}/v1/jobs/job_1").mock(
        return_value=httpx.Response(200, json={"id": "job_1", "status": "completed"})
    )

    with make_client() as client:
        job = client.tag_pdf(pdf, wait=False)

    assert job.status == "processing"
    assert not job_route.called  # never polled


@respx.mock
def test_tag_pdf_raises_job_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda *_: None)
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")

    respx.post(f"{BASE}/v1/uploads").mock(
        return_value=httpx.Response(
            201, json={"upload_url": "https://s3.example.com/upload", "fields": {"key": "u/1.pdf"}, "key": "u/1.pdf"}
        )
    )
    respx.post("https://s3.example.com/upload").mock(return_value=httpx.Response(204))
    respx.post(f"{BASE}/v1/jobs").mock(return_value=httpx.Response(202, json={"id": "job_1", "status": "processing"}))
    respx.get(f"{BASE}/v1/jobs/job_1").mock(return_value=httpx.Response(200, json={"id": "job_1", "status": "failed"}))

    with make_client() as client:
        with pytest.raises(JobFailed) as exc:
            client.tag_pdf(pdf)
    assert exc.value.job is not None
    assert exc.value.job.status == "failed"


@respx.mock
def test_wait_for_job_times_out(monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda *_: None)
    # monotonic jumps past the deadline on the second read.
    ticks = iter([0.0, 0.0, 10_000.0, 10_000.0])
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(ticks))

    respx.get(f"{BASE}/v1/jobs/job_1").mock(
        return_value=httpx.Response(200, json={"id": "job_1", "status": "processing"})
    )

    with make_client() as client:
        with pytest.raises(JobTimeout):
            client.wait_for_job("job_1", poll_timeout=60.0)


@respx.mock
def test_wait_for_job_retries_on_rate_limit(monkeypatch):
    slept = []
    monkeypatch.setattr(client_module.time, "sleep", lambda s: slept.append(s))

    respx.get(f"{BASE}/v1/jobs/job_1").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "5"}, json={"error": {"message": "slow"}}),
            httpx.Response(200, json={"id": "job_1", "status": "completed"}),
        ]
    )

    with make_client() as client:
        job = client.wait_for_job("job_1", poll_interval=3.0)

    assert job.succeeded
    assert slept == [5]  # waited the Retry-After, not the poll interval


@respx.mock
def test_download_result_bytes_and_file(tmp_path):
    respx.get(f"{BASE}/v1/jobs/job_1/result").mock(
        return_value=httpx.Response(200, json={"result_url": "https://s3.example.com/out.pdf", "expires_in": 600})
    )
    respx.get("https://s3.example.com/out.pdf").mock(return_value=httpx.Response(200, content=b"%PDF-tagged"))

    with make_client() as client:
        data = client.download_result("job_1")
        assert data == b"%PDF-tagged"

        dest = tmp_path / "out.pdf"
        written = client.download_result("job_1", dest)
        assert written == dest
        assert dest.read_bytes() == b"%PDF-tagged"
