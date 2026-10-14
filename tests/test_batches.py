"""Unit tests for the batch methods, with the HTTP layer mocked by respx."""

import hashlib
import hmac
import json

import httpx
import pytest
import respx

import pdftagger.client as client_module
from pdftagger import BadRequestError, BatchItem, InsufficientCreditsError, JobTimeout, PdfTaggerClient, verify_signature
from pdftagger.client import BATCH_SUBMIT_TIMEOUT, _unique_names

BASE = "https://api.pdf-tagger.com"


def job(id_, status="processing", filename="a.pdf", **extra):
    return {"id": id_, "status": status, "filename": filename, "credits_used": 1, **extra}


def batch(status="processing", jobs=None, **extra):
    jobs = jobs if jobs is not None else [job("j1"), job("j2", filename="b.pdf")]
    done = [j for j in jobs if j["status"] != "processing"]
    return {
        "id": "b1",
        "name": "2 documents, Oct 14, 2026",
        "status": status,
        "counts": {
            "total": len(jobs),
            "processing": len(jobs) - len(done),
            "completed": sum(j["status"] == "completed" for j in jobs),
            "failed": sum(j["status"] == "failed" for j in jobs),
        },
        "credits_used": 2,
        "created_at": "2026-10-14T00:00:00Z",
        "completed_at": None,
        "jobs": jobs,
        **extra,
    }


def make_client():
    return PdfTaggerClient(api_key="sk_live_test")


@respx.mock
def test_submit_batch_sends_keys_items_options_name_and_idempotency():
    route = respx.post(f"{BASE}/v1/batches").mock(return_value=httpx.Response(202, json=batch()))
    with make_client() as client:
        result = client.submit_batch(
            ["u/1.pdf", BatchItem(key="u/2.pdf", filename="b.pdf", ocr=True)],
            name="Q3",
            idempotency_key="idem-1",
        )
    request = route.calls.last.request
    assert json.loads(request.content) == {
        "jobs": [{"key": "u/1.pdf"}, {"key": "u/2.pdf", "filename": "b.pdf", "options": {"ocr": True}}],
        "name": "Q3",
    }
    assert request.headers["idempotency-key"] == "idem-1"
    assert result.id == "b1"
    assert [j.id for j in result.jobs] == ["j1", "j2"]
    assert result.counts.total == 2 and result.counts.processing == 2
    assert not result.is_terminal


def test_submit_batch_uses_the_long_timeout():
    seen = {}

    def handler(request):
        seen["timeout"] = request.extensions["timeout"]
        return httpx.Response(202, json=batch())

    with PdfTaggerClient(api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(handler), timeout=30)) as client:
        client.submit_batch(["u/1.pdf"])
    assert seen["timeout"]["read"] == BATCH_SUBMIT_TIMEOUT


@respx.mock
def test_a_refused_batch_raises_with_one_error_per_bad_job():
    respx.post(f"{BASE}/v1/batches").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request",
                    "message": "1 job has a problem. Nothing was charged. See `errors`.",
                    "request_id": "req_1",
                    "errors": [{"index": 1, "type": "too_many_pages", "message": "Too many pages."}],
                }
            },
        )
    )
    with make_client() as client, pytest.raises(BadRequestError) as excinfo:
        client.submit_batch(["u/1.pdf", "u/2.pdf"])
    assert excinfo.value.errors == [{"index": 1, "type": "too_many_pages", "message": "Too many pages."}]
    assert excinfo.value.request_id == "req_1"


@respx.mock
def test_too_few_credits_raises_insufficient_credits_with_no_job_errors():
    respx.post(f"{BASE}/v1/batches").mock(
        return_value=httpx.Response(402, json={"error": {"type": "insufficient_credits", "message": "needs 3"}})
    )
    with make_client() as client, pytest.raises(InsufficientCreditsError) as excinfo:
        client.submit_batch(["u/1.pdf"])
    assert excinfo.value.errors == []


@respx.mock
def test_get_batch_reads_failed_job_details():
    respx.get(f"{BASE}/v1/batches/b1").mock(
        return_value=httpx.Response(
            200,
            json=batch(
                "completed",
                [job("j1", "completed"), job("j2", "failed", error_code="ENCRYPTED", error_message="Encrypted.")],
            ),
        )
    )
    with make_client() as client:
        result = client.get_batch("b1")
    assert result.is_terminal
    assert [j.id for j in result.completed_jobs] == ["j1"]
    assert result.failed_jobs[0].error_code == "ENCRYPTED"


@respx.mock
def test_tag_pdfs_uploads_each_file_submits_one_batch_and_waits(tmp_path, monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda *_: None)
    files = []
    for n in ("a.pdf", "b.pdf"):
        p = tmp_path / n
        p.write_bytes(b"%PDF-1.7 fake")
        files.append(p)
    uploads = iter(
        httpx.Response(201, json={"upload_url": "https://s3.example.com/up", "fields": {"key": k}, "key": k})
        for k in ("u/a.pdf", "u/b.pdf")
    )
    respx.post(f"{BASE}/v1/uploads").mock(side_effect=lambda request: next(uploads))
    s3 = respx.post("https://s3.example.com/up").mock(return_value=httpx.Response(204))
    submit = respx.post(f"{BASE}/v1/batches").mock(return_value=httpx.Response(202, json=batch()))
    polls = iter([batch(), batch("completed", [job("j1", "completed"), job("j2", "failed", filename="b.pdf")])])
    respx.get(f"{BASE}/v1/batches/b1").mock(side_effect=lambda request: httpx.Response(200, json=next(polls)))

    with make_client() as client:
        result = client.tag_pdfs(files, ocr=True)

    assert s3.call_count == 2
    assert json.loads(submit.calls.last.request.content)["jobs"] == [
        {"key": "u/a.pdf", "filename": "a.pdf", "options": {"ocr": True}},
        {"key": "u/b.pdf", "filename": "b.pdf", "options": {"ocr": True}},
    ]
    # A failed job does not raise for a batch.
    assert result.is_terminal and len(result.failed_jobs) == 1


@respx.mock
def test_tag_pdfs_without_wait_returns_the_accepted_batch(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.7 fake")
    respx.post(f"{BASE}/v1/uploads").mock(
        return_value=httpx.Response(201, json={"upload_url": "https://s3.example.com/up", "fields": {}, "key": "u/a.pdf"})
    )
    respx.post("https://s3.example.com/up").mock(return_value=httpx.Response(204))
    respx.post(f"{BASE}/v1/batches").mock(return_value=httpx.Response(202, json=batch()))
    get = respx.get(f"{BASE}/v1/batches/b1")
    with make_client() as client:
        result = client.tag_pdfs([p], wait=False)
    assert result.status == "processing" and get.call_count == 0


@respx.mock
def test_wait_for_batch_times_out(monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda *_: None)
    clock = iter([0.0, 0.0, 100.0, 200.0])
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(clock))
    respx.get(f"{BASE}/v1/batches/b1").mock(return_value=httpx.Response(200, json=batch()))
    with make_client() as client, pytest.raises(JobTimeout):
        client.wait_for_batch("b1", poll_timeout=50)


@respx.mock
def test_download_batch_results_saves_completed_jobs_with_unique_names(tmp_path):
    done = batch(
        "completed",
        [job("j1", "completed", "r.pdf"), job("j2", "failed", "x.pdf"), job("j3", "completed", "r.pdf")],
    )
    for jid in ("j1", "j3"):
        respx.get(f"{BASE}/v1/jobs/{jid}/result").mock(
            return_value=httpx.Response(200, json={"result_url": f"https://s3.example.com/{jid}", "expires_in": 3600})
        )
        respx.get(f"https://s3.example.com/{jid}").mock(return_value=httpx.Response(200, content=jid.encode()))
    with make_client() as client:
        from pdftagger import Batch

        paths = client.download_batch_results(Batch.from_dict(done), tmp_path / "out")
    assert [p.name for p in paths] == ["r.pdf", "r (2).pdf"]
    assert [p.read_bytes() for p in paths] == [b"j1", b"j3"]


def test_unique_names():
    assert _unique_names(["a.pdf", "A.pdf", "a.pdf", "noext", "dir/b.pdf"]) == [
        "a.pdf",
        "A (2).pdf",
        "a (3).pdf",
        "noext",
        "b.pdf",
    ]


def test_batch_completed_webhook_parses_the_batch():
    body = json.dumps(
        {
            "id": "evt_1",
            "type": "batch.completed",
            "created": 1760000000,
            "data": {"batch": {"id": "b1", "name": "B", "status": "completed", "total": 3, "completed": 2, "failed": 1}},
        }
    ).encode()
    t = 1760000000
    sig = hmac.new(b"whsec_x", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    event = verify_signature(body, f"t={t},v1={sig}", "whsec_x", now=t)
    assert event.type == "batch.completed"
    assert event.job is None
    assert event.batch.id == "b1" and event.batch.completed == 2 and event.batch.failed == 1
