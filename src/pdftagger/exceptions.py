"""Exception hierarchy for the PDF Tagger SDK.

Every error the SDK raises derives from :class:`PdfTaggerError`, so a caller can catch
that one type to handle anything the SDK can throw. API responses map to a specific
subclass of :class:`APIError` by status code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # avoid a runtime import cycle (models imports nothing from here)
    from .models import Job


class PdfTaggerError(Exception):
    """Base class for every error raised by the SDK."""


class APIError(PdfTaggerError):
    """An error returned by the API, or an unexpected HTTP/transport failure.

    Attributes:
        status_code: The HTTP status code, when the failure came from a response.
        type: The API error ``type`` string, when the body carried one.
        request_id: The request id for support, from the body or the ``X-Request-Id`` header.
        errors: On a refused batch (``POST /v1/batches``), one entry for each bad job:
            ``{"index": <place in jobs, from 0>, "type": ..., "message": ...}``. Otherwise empty.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        type: Optional[str] = None,
        request_id: Optional[str] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.type = type
        self.request_id = request_id
        self.errors: List[Dict[str, Any]] = list(errors or [])


class BadRequestError(APIError):
    """HTTP 400 — the request was invalid."""


class AuthenticationError(APIError):
    """HTTP 401 — the API key is missing, invalid, or revoked."""


class InsufficientCreditsError(APIError):
    """HTTP 402 — the account does not have enough credits for the job."""


class NotFoundError(APIError):
    """HTTP 404 — no such resource for this account."""


class ConflictError(APIError):
    """HTTP 409 — an idempotency conflict, or a resource not ready yet."""


class RateLimitError(APIError):
    """HTTP 429 — the rate limit was exceeded.

    Attributes:
        retry_after: Seconds to wait before retrying, from the ``Retry-After`` header.
    """

    def __init__(self, message: str, *, retry_after: Optional[int] = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class JobTimeout(PdfTaggerError):
    """A job did not reach a terminal state within the poll timeout.

    Attributes:
        job: The last :class:`~pdftagger.models.Job` observed, if any.
    """

    def __init__(self, message: str, *, job: "Optional[Job]" = None) -> None:
        super().__init__(message)
        self.job = job


class JobFailed(PdfTaggerError):
    """A job reached a terminal ``failed`` status while waiting for it.

    Credits for a failed job are refunded automatically by the service.

    Attributes:
        job: The failed :class:`~pdftagger.models.Job`.
    """

    def __init__(self, message: str, *, job: "Optional[Job]" = None) -> None:
        super().__init__(message)
        self.job = job


class WebhookVerificationError(PdfTaggerError):
    """A webhook signature could not be verified (bad signature, format, or replay)."""
