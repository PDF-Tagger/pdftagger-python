"""Tests for the PDF/UA-1 report: get_job_report, download_report and the report models."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from pdftagger import ConflictError, JobReport, NotFoundError, PdfTaggerClient, Requirement

BASE = "https://api.pdf-tagger.com"

# A real GET /v1/jobs/{id}/report body from the local server (2026-10-31), with the signed URL replaced.
REPORT = json.loads((Path(__file__).parent / "fixtures" / "job_report.json").read_text(encoding="utf-8"))


def make_client() -> PdfTaggerClient:
    return PdfTaggerClient(api_key="sk_live_test")


def err(status: int, type_: str) -> httpx.Response:
    return httpx.Response(status, json={"error": {"type": type_, "message": f"boom {status}"}})


@respx.mock
def test_get_job_report_parses_every_requirement():
    route = respx.get(f"{BASE}/v1/jobs/job_1/report").mock(return_value=httpx.Response(200, json=REPORT))
    with make_client() as client:
        report = client.get_job_report("job_1")

    assert route.called
    assert isinstance(report, JobReport)
    assert report.job_id == "job_1"
    assert report.standard == "PDF/UA-1 (ISO 14289-1:2014)"
    assert report.total_requirements == 220
    assert len(report.requirements) == 220
    assert sum(report.summary.values()) == 220
    assert report.report_pdf_url == "https://s3.example.com/report.pdf"
    assert report.expires_in == 3600

    first = report.requirements[0]
    assert isinstance(first, Requirement)
    assert first.id == "L1-5-1"
    assert first.reference.startswith("ISO 14289-1")
    assert first.section_id == "5"
    assert first.section_title == "Version identification"
    assert first.category == "Document setup & metadata"
    assert first.level == "shall"
    assert first.result == "handled"
    assert first.evidence is None
    assert first.raw["section"] == {"id": "5", "title": "Version identification"}


@respx.mock
def test_failed_and_needs_review_filter_by_result():
    body = {
        "job_id": "job_1",
        "standard": "PDF/UA-1 (ISO 14289-1:2014)",
        "total_requirements": 3,
        "summary": {"handled": 1, "failed": 1, "needs_review": 1},
        "requirements": [
            {"id": "a", "reference": "ISO 14289-1 §7.1", "name": "A", "result": "handled"},
            {"id": "b", "reference": "ISO 14289-1 §7.21", "name": "B", "result": "failed", "evidence": "2 instances in this file."},
            {"id": "c", "reference": "ISO 14289-1 §7.3", "name": "C", "result": "needs_review"},
        ],
        "report_pdf_url": None,
    }
    respx.get(f"{BASE}/v1/jobs/job_1/report").mock(return_value=httpx.Response(200, json=body))
    with make_client() as client:
        report = client.get_job_report("job_1")

    assert [r.id for r in report.failed] == ["b"]
    assert report.failed[0].evidence == "2 instances in this file."
    assert [r.id for r in report.needs_review] == ["c"]
    assert report.report_pdf_url is None


@respx.mock
def test_get_job_report_errors():
    respx.get(f"{BASE}/v1/jobs/busy/report").mock(return_value=err(409, "not_ready"))
    respx.get(f"{BASE}/v1/jobs/old/report").mock(return_value=err(404, "report_unavailable"))
    with make_client() as client:
        with pytest.raises(ConflictError) as busy:
            client.get_job_report("busy")
        with pytest.raises(NotFoundError) as old:
            client.get_job_report("old")
    assert busy.value.type == "not_ready"
    assert old.value.type == "report_unavailable"


@respx.mock
def test_download_report_bytes_and_file(tmp_path):
    respx.get(f"{BASE}/v1/jobs/job_1/report").mock(return_value=httpx.Response(200, json=REPORT))
    respx.get("https://s3.example.com/report.pdf").mock(return_value=httpx.Response(200, content=b"%PDF-report"))

    with make_client() as client:
        assert client.download_report("job_1") == b"%PDF-report"
        dest = tmp_path / "report.pdf"
        assert client.download_report("job_1", dest) == dest
    assert dest.read_bytes() == b"%PDF-report"


@respx.mock
def test_download_report_when_the_pdf_is_gone():
    respx.get(f"{BASE}/v1/jobs/job_1/report").mock(
        return_value=httpx.Response(200, json={**REPORT, "report_pdf_url": None})
    )
    with make_client() as client:
        with pytest.raises(NotFoundError):
            client.download_report("job_1")
