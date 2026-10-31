# Scope: pdftagger 0.2.0 — the PDF/UA-1 report

## Problem
1. The API gains `GET /v1/jobs/{id}/report` (open-saas-pdftagger, branch `api-job-report`): the result and evidence
   for each of the 220 accessibility requirements in PDF/UA-1, and a link to the report PDF. The SDK has no way to
   read it.
2. PyPI shows a "Change of provenance" banner on the project page. 0.1.0 came from `rachel-ackeret/pdftagger-python`
   and 0.1.1 from `PDF-Tagger/pdftagger-python`, so PyPI flagged 0.1.1.

## How the release clears the banner
PyPI (warehouse source, `Release.comparison_provenance_release`) compares a release with the latest earlier release
that has attestations and was made within 14 days. It warns when the publisher repo or workflow changed. 0.2.0 comes
from the same org repo and `publish.yml` as 0.1.1, so it gets no warning, and the project page shows 0.2.0. The
warning stays on 0.1.1's own page; only deleting 0.1.0 would remove it, and we do not do that. Rachel wants one
release: 0.2.0 replaces the planned 0.1.2 (PR #1, closed).

## Design
- `PdfTaggerClient.get_job_report(job) -> JobReport`.
- `PdfTaggerClient.download_report(job, dest=None)`: the report PDF, like `download_result`.
- Models: `JobReport` (`standard`, `total_requirements`, `summary`, `requirements`, `report_pdf_url`,
  `expires_in`) and `Requirement` (`id`, `reference`, `name`, `level`, `section_id`, `section_title`, `category`,
  `result`, `evidence`). Helpers: `JobReport.failed`, `JobReport.needs_review`. Unknown fields stay in `raw`.
- `NotFoundError` for a job with no report (`report_unavailable`), `ConflictError` before the job completes: the
  existing error mapping already does this.

## Constraints
- Release only after the API endpoint is deployed: the new methods call it.
- Release through trusted publishing (`RELEASING.md`). Commits as PDF Tagger <support@pdf-tagger.com>, with no
  Claude attribution.
