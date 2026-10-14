"""Typed data models returned by the SDK.

Each model keeps the full server payload in ``raw`` so a new API field is always
reachable even before the SDK adds a typed attribute for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Union

# Terminal job statuses (the job will not change again).
COMPLETED = "completed"
FAILED = "failed"
PROCESSING = "processing"
TERMINAL_STATUSES = (COMPLETED, FAILED)


@dataclass
class Account:
    """The authenticated account and its credit balance (``GET /v1/me``)."""

    account_id: Optional[str] = None
    plan: Optional[str] = None
    subscription_status: Optional[str] = None
    credits_available: Optional[int] = None
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Account":
        return cls(
            account_id=data.get("account_id"),
            plan=data.get("plan"),
            subscription_status=data.get("subscription_status"),
            credits_available=data.get("credits_available"),
            request_id=data.get("request_id"),
            raw=dict(data),
        )


@dataclass
class Upload:
    """A presigned upload target (``POST /v1/uploads``).

    Pass ``key`` to :meth:`~pdftagger.client.PdfTaggerClient.submit_job` after the file
    has been uploaded to ``upload_url`` with every entry in ``fields``.
    """

    upload_url: str
    fields: Dict[str, str]
    key: str
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Upload":
        return cls(
            upload_url=data["upload_url"],
            fields=dict(data.get("fields") or {}),
            key=data["key"],
            request_id=data.get("request_id"),
            raw=dict(data),
        )


@dataclass
class Job:
    """A tagging job (``POST /v1/jobs`` and ``GET /v1/jobs/{id}``)."""

    id: str
    status: str
    filename: Optional[str] = None
    credits_used: Optional[int] = None
    options: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    request_id: Optional[str] = None
    #: Why the job failed. Set on the jobs inside a :class:`Batch` and in job webhook events.
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Job":
        return cls(
            id=data["id"],
            status=data["status"],
            filename=data.get("filename"),
            credits_used=data.get("credits_used"),
            options=data.get("options"),
            created_at=data.get("created_at"),
            request_id=data.get("request_id"),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            raw=dict(data),
        )

    @property
    def is_terminal(self) -> bool:
        """True once the job is ``completed`` or ``failed``."""
        return self.status in TERMINAL_STATUSES

    @property
    def succeeded(self) -> bool:
        """True only when the job is ``completed``."""
        return self.status == COMPLETED


@dataclass
class JobResult:
    """A short-lived download link for a finished job (``GET /v1/jobs/{id}/result``)."""

    result_url: str
    expires_in: Optional[int] = None
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JobResult":
        return cls(
            result_url=data["result_url"],
            expires_in=data.get("expires_in"),
            request_id=data.get("request_id"),
            raw=dict(data),
        )


@dataclass
class BatchItem:
    """One file in a batch for :meth:`~pdftagger.client.PdfTaggerClient.submit_batch`.

    ``key`` comes from :meth:`~pdftagger.client.PdfTaggerClient.create_upload`.
    """

    key: str
    filename: Optional[str] = None
    ocr: bool = False
    embed_fonts: bool = False

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"key": self.key}
        if self.filename:
            payload["filename"] = self.filename
        options: Dict[str, bool] = {}
        if self.ocr:
            options["ocr"] = True
        if self.embed_fonts:
            options["embed_fonts"] = True
        if options:
            payload["options"] = options
        return payload


@dataclass
class BatchCounts:
    """How many jobs in a batch are in each status."""

    total: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BatchCounts":
        return cls(
            total=data.get("total", 0),
            processing=data.get("processing", 0),
            completed=data.get("completed", 0),
            failed=data.get("failed", 0),
        )


@dataclass
class Batch:
    """A batch of jobs (``POST /v1/batches`` and ``GET /v1/batches/{id}``).

    ``status`` is ``completed`` once every job has finished, whether each job completed
    or failed. ``jobs`` keeps the order of the request.
    """

    id: str
    status: str
    name: Optional[str] = None
    counts: BatchCounts = field(default_factory=BatchCounts)
    credits_used: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    jobs: List[Job] = field(default_factory=list)
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Batch":
        return cls(
            id=data["id"],
            status=data["status"],
            name=data.get("name"),
            counts=BatchCounts.from_dict(data.get("counts") or {}),
            credits_used=data.get("credits_used"),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
            jobs=[Job.from_dict(j) for j in data.get("jobs") or []],
            request_id=data.get("request_id"),
            raw=dict(data),
        )

    @property
    def is_terminal(self) -> bool:
        """True once every job in the batch has finished."""
        return self.status == COMPLETED

    @property
    def completed_jobs(self) -> List[Job]:
        """The jobs whose tagged PDF is ready to download."""
        return [j for j in self.jobs if j.status == COMPLETED]

    @property
    def failed_jobs(self) -> List[Job]:
        """The jobs that failed. Their credits are refunded."""
        return [j for j in self.jobs if j.status == FAILED]


@dataclass
class BatchEvent:
    """The batch data in a ``batch.completed`` webhook event."""

    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    total: int = 0
    completed: int = 0
    failed: int = 0
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BatchEvent":
        return cls(
            id=data["id"],
            name=data.get("name"),
            status=data.get("status"),
            total=data.get("total", 0),
            completed=data.get("completed", 0),
            failed=data.get("failed", 0),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
        )


@dataclass
class WebhookEvent:
    """A verified webhook event: ``job.completed``, ``job.failed`` or ``batch.completed``.

    A job event sets ``job``; a ``batch.completed`` event sets ``batch``. The event carries
    no result URL — fetch it with
    :meth:`~pdftagger.client.PdfTaggerClient.get_job_result`, or read a batch's jobs with
    :meth:`~pdftagger.client.PdfTaggerClient.get_batch`.
    """

    id: Optional[str]
    type: str
    created: Optional[int]
    job: Optional[Job]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    batch: Optional[BatchEvent] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WebhookEvent":
        body = data.get("data") or {}
        job_data = body.get("job")
        batch_data = body.get("batch")
        return cls(
            id=data.get("id"),
            type=data.get("type", ""),
            created=data.get("created"),
            job=Job.from_dict(job_data) if job_data else None,
            raw=dict(data),
            batch=BatchEvent.from_dict(batch_data) if batch_data else None,
        )


BatchItemInput = Union[str, BatchItem]
