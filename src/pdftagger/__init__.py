"""Official Python SDK for the PDF Tagger API.

Auto-tag PDFs for PDF/UA accessibility from your own code:

    >>> from pdftagger import PdfTaggerClient
    >>> client = PdfTaggerClient(api_key="sk_live_...")
    >>> job = client.tag_pdf("report.pdf", ocr=True)
    >>> client.download_result(job, "report.tagged.pdf")

Many PDFs at once, as one batch:

    >>> batch = client.tag_pdfs(["a.pdf", "b.pdf", "c.pdf"])
    >>> client.download_batch_results(batch, "tagged/")
"""

from __future__ import annotations

from ._version import __version__
from .client import DEFAULT_BASE_URL, PdfTaggerClient
from .exceptions import (
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InsufficientCreditsError,
    JobFailed,
    JobTimeout,
    NotFoundError,
    PdfTaggerError,
    RateLimitError,
    WebhookVerificationError,
)
from .models import Account, Batch, BatchCounts, BatchEvent, BatchItem, Job, JobResult, Upload, WebhookEvent
from .webhooks import SIGNATURE_HEADER, verify_signature

__all__ = [
    "__version__",
    "PdfTaggerClient",
    "DEFAULT_BASE_URL",
    # models
    "Account",
    "Upload",
    "Job",
    "JobResult",
    "Batch",
    "BatchItem",
    "BatchCounts",
    "BatchEvent",
    "WebhookEvent",
    # webhooks
    "verify_signature",
    "SIGNATURE_HEADER",
    # exceptions
    "PdfTaggerError",
    "APIError",
    "BadRequestError",
    "AuthenticationError",
    "InsufficientCreditsError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "JobTimeout",
    "JobFailed",
    "WebhookVerificationError",
]
