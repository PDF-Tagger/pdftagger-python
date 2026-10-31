# pdftagger — auto-tag PDFs for accessibility from Python

Official Python SDK for the [PDF Tagger](https://pdf-tagger.com) API. Upload a PDF,
submit a tagging job, and download a **PDF/UA-tagged, accessible** PDF — with correct
reading order, headings, tables, and alt text. Tag one PDF, or up to 100 at once as a batch.
Each job comes with a PDF/UA-1 report: the result for every accessibility requirement in PDF/UA-1.

```bash
pip install pdftagger
```

## How to auto-tag PDFs with the PDF Tagger SDK

Get an API key from the [Developers page](https://pdf-tagger.com/developers), then:

```python
from pdftagger import PdfTaggerClient

client = PdfTaggerClient(api_key="sk_live_...")

# Upload, submit, and wait for the tagged PDF — one call.
job = client.tag_pdf("report.pdf", ocr=True)

# Save the accessible, tagged PDF.
client.download_result(job, "report.tagged.pdf")
```

That's the whole flow. `tag_pdf()` uploads the file, submits the job, polls until it
finishes, and returns the completed job. Each job costs one credit per page, drawn from
the same balance as the web app.

### Options

```python
job = client.tag_pdf(
    "scan.pdf",
    ocr=True,            # recover text from image-only / scanned pages
    embed_fonts=True,    # embed a non-embedded font where it is safe to do so
    idempotency_key="order-1234",  # safe to retry without double-charging
)
```

Don't want to block? Submit and poll yourself:

```python
job = client.tag_pdf("report.pdf", wait=False)   # returns immediately
job = client.wait_for_job(job)                    # ...poll later
```

## The PDF/UA-1 report

Every completed job has a report: the result and evidence for every accessibility requirement in
PDF/UA-1, and a report PDF you can keep.

```python
report = client.get_job_report(job)
print(report.summary)   # {'handled': 169, 'failed': 0, 'needs_review': 0, 'for_information': 0, 'not_applicable': 51}

for req in report.failed:   # also report.needs_review
    print(req.reference, req.name, req.evidence)

client.download_report(job, "report.accessibility-report.pdf")
```

Each `Requirement` has a `result`:

| `result` | Meaning |
|---|---|
| `handled` | It passed, or PDF Tagger met or fixed it. |
| `failed` | A validator found it failing in the file. |
| `needs_review` | A person must confirm it. |
| `for_information` | A limit from the source file that you cannot act on. |
| `not_applicable` | The document has no content of this kind. |

## Many PDFs at once: batches

Tag up to 100 PDFs as one batch. `tag_pdfs()` uploads every file, submits them in one
request, and waits until every job has finished:

```python
batch = client.tag_pdfs(["a.pdf", "b.pdf", "c.pdf"], name="Q3 reports", ocr=True)

print(batch.counts)                 # BatchCounts(total=3, processing=0, completed=3, failed=0)
for job in batch.failed_jobs:       # a failed job does not raise for a batch
    print(job.filename, job.error_code, job.error_message)

client.download_batch_results(batch, "tagged/")   # saves each completed PDF
```

A batch is **all or nothing**: if any file is not a PDF, has more than 750 pages, or the
credits do not cover every page, nothing is charged and the call raises.
`BadRequestError.errors` lists each bad file by its position:

```python
from pdftagger import BadRequestError

try:
    client.submit_batch([upload_a.key, upload_b.key])
except BadRequestError as e:
    for problem in e.errors:        # {"index": 1, "type": "too_many_pages", "message": "..."}
        print(problem["index"], problem["message"])
```

Drive it yourself with `submit_batch()` (upload keys or `BatchItem`s), `get_batch()` and
`wait_for_batch()`. Each job in a batch is a normal job, so `get_job()`,
`get_job_result()` and `download_result()` work on it.

## Verifying webhooks

Register a webhook endpoint on the Developers page to be notified when a job finishes.
Verify every delivery before trusting it — pass the **raw** request body:

```python
from pdftagger import verify_signature
from pdftagger.webhooks import SIGNATURE_HEADER

event = verify_signature(
    payload=raw_body_bytes,                 # the exact bytes you received
    header=request.headers[SIGNATURE_HEADER],
    secret="whsec_...",                     # the endpoint secret
)

if event.type == "job.completed":
    url = client.get_job_result(event.job.id).result_url
elif event.type == "batch.completed":
    batch = client.get_batch(event.batch.id)    # every job in the batch has finished
```

`verify_signature` recomputes the HMAC-SHA256 signature over the raw body, compares it in
constant time, and rejects a stale timestamp (replay). It raises
`WebhookVerificationError` on any failure. A delivery can arrive more than once, so
dedupe on `event.id`.

## Low-level API

Every endpoint is available directly if you want to drive the flow yourself:

```python
client.get_account()                       # account + credit balance
upload = client.create_upload("report.pdf")
client.upload_file(upload, "report.pdf")
job = client.submit_job(key=upload.key, ocr=True)
job = client.get_job(job.id)               # processing / completed / failed
result = client.get_job_result(job.id)     # short-lived download URL
report = client.get_job_report(job.id)     # the PDF/UA-1 report
```

## Errors

All errors derive from `PdfTaggerError`.

| Exception | When |
|---|---|
| `AuthenticationError` | 401 — key missing, invalid, or revoked |
| `BadRequestError` | 400 — invalid request (for a batch, `.errors` lists each bad file) |
| `InsufficientCreditsError` | 402 — not enough credits (a batch charges nothing) |
| `NotFoundError` | 404 — no such job/resource for this account, or the job has no report |
| `ConflictError` | 409 — idempotency conflict, or result or report not ready |
| `RateLimitError` | 429 — rate limited (`.retry_after` seconds) |
| `JobFailed` | the job finished with a `failed` status (credits are refunded) |
| `JobTimeout` | the job, or the batch, did not finish within the poll timeout |
| `WebhookVerificationError` | a webhook signature could not be verified |

## Requirements

- Python 3.9+
- [`httpx`](https://www.python-httpx.org/) (installed automatically)

## Links

- API reference: https://pdf-tagger.com/api/reference
- Create an API key: https://pdf-tagger.com/developers

## License

MIT
