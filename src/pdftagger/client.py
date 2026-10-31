"""The synchronous PDF Tagger API client."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Sequence, Union

import httpx

from ._version import __version__
from .exceptions import (
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InsufficientCreditsError,
    JobFailed,
    JobTimeout,
    NotFoundError,
    RateLimitError,
)
from .models import Account, Batch, BatchItem, BatchItemInput, Job, JobReport, JobResult, Upload

DEFAULT_BASE_URL = "https://api.pdf-tagger.com"

#: Seconds to wait for ``POST /v1/batches``. The API reads every file before it answers, so a
#: batch takes longer to accept than one job.
BATCH_SUBMIT_TIMEOUT = 300.0

# status code -> exception class (429 is handled separately to read Retry-After)
_ERROR_BY_STATUS = {
    400: BadRequestError,
    401: AuthenticationError,
    402: InsufficientCreditsError,
    404: NotFoundError,
    409: ConflictError,
}

FileInput = Union[str, Path, BinaryIO]


class PdfTaggerClient:
    """A client for the PDF Tagger API.

    Args:
        api_key: Your API key (``sk_live_…``).
        base_url: Override the API base URL (for testing or a private deployment).
        timeout: Per-request timeout in seconds.
        http_client: Supply your own ``httpx.Client`` (its lifecycle is then yours).

    Example:
        >>> from pdftagger import PdfTaggerClient
        >>> with PdfTaggerClient(api_key="sk_live_...") as client:
        ...     job = client.tag_pdf("report.pdf", ocr=True)
        ...     client.download_result(job, "report.tagged.pdf")
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout)

    # -- lifecycle ---------------------------------------------------------------

    def __enter__(self) -> "PdfTaggerClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client (only if the SDK created it)."""
        if self._owns_client:
            self._http.close()

    # -- low-level request plumbing ---------------------------------------------

    def _auth_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": f"pdftagger-python/{__version__}",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        extra: Dict[str, Any] = {"timeout": timeout} if timeout is not None else {}
        try:
            response = self._http.request(method, url, json=json, headers=self._auth_headers(headers), **extra)
        except httpx.HTTPError as exc:
            raise APIError(f"HTTP request to {path} failed: {exc}") from exc
        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        request_id = response.headers.get("X-Request-Id")

        if response.is_success:
            if response.status_code == 204 or not response.content:
                return {}
            try:
                return response.json()
            except ValueError:
                return {}

        error_type: Optional[str] = None
        message: Optional[str] = None
        job_errors: List[Dict[str, Any]] = []
        try:
            body = response.json()
            error = body.get("error") or {}
            error_type = error.get("type")
            message = error.get("message")
            request_id = error.get("request_id") or request_id
            job_errors = list(error.get("errors") or [])
        except ValueError:
            message = response.text or None

        message = message or f"HTTP {response.status_code}"
        common = {
            "status_code": response.status_code,
            "type": error_type,
            "request_id": request_id,
            "errors": job_errors,
        }

        if response.status_code == 429:
            raw_retry = response.headers.get("Retry-After")
            retry_after = int(raw_retry) if raw_retry and raw_retry.isdigit() else None
            raise RateLimitError(message, retry_after=retry_after, **common)

        error_cls = _ERROR_BY_STATUS.get(response.status_code, APIError)
        raise error_cls(message, **common)

    # -- endpoints (1:1 with the API) -------------------------------------------

    def get_account(self) -> Account:
        """Return the authenticated account and its credit balance."""
        return Account.from_dict(self._request("GET", "/v1/me"))

    def create_upload(self, filename: Optional[str] = None) -> Upload:
        """Create a presigned upload target. Follow with :meth:`upload_file`."""
        payload: Dict[str, Any] = {}
        if filename:
            payload["filename"] = filename
        return Upload.from_dict(self._request("POST", "/v1/uploads", json=payload))

    def upload_file(self, upload: Upload, file: FileInput) -> None:
        """Upload the PDF bytes to the presigned target from :meth:`create_upload`.

        The presigned POST requires every field from ``upload.fields`` to precede the
        file part, which this method guarantees.
        """
        fh: BinaryIO
        should_close = False
        if isinstance(file, (str, Path)):
            fh = open(file, "rb")
            should_close = True
            filename = Path(file).name
        else:
            fh = file
            filename = getattr(file, "name", None) or "document.pdf"
            filename = Path(str(filename)).name

        try:
            # httpx serializes `data` (the presigned fields) before `files`, so the file
            # part comes last — which is what S3 requires.
            files = {"file": (filename, fh, "application/pdf")}
            response = self._http.post(upload.upload_url, data=dict(upload.fields), files=files)
        except httpx.HTTPError as exc:
            raise APIError(f"Upload to storage failed: {exc}") from exc
        finally:
            if should_close:
                fh.close()

        if not response.is_success:
            raise APIError(
                f"Upload to storage failed: HTTP {response.status_code}",
                status_code=response.status_code,
            )

    def submit_job(
        self,
        *,
        key: str,
        ocr: bool = False,
        embed_fonts: bool = False,
        filename: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Job:
        """Submit a tagging job for an uploaded ``key``. Charges one credit per page."""
        options: Dict[str, bool] = {}
        if ocr:
            options["ocr"] = True
        if embed_fonts:
            options["embed_fonts"] = True

        payload: Dict[str, Any] = {"key": key}
        if filename:
            payload["filename"] = filename
        if options:
            payload["options"] = options

        headers: Dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        return Job.from_dict(self._request("POST", "/v1/jobs", json=payload, headers=headers))

    def get_job(self, job: Union[str, Job]) -> Job:
        """Fetch a job's current status."""
        return Job.from_dict(self._request("GET", f"/v1/jobs/{_job_id(job)}"))

    def get_job_result(self, job: Union[str, Job]) -> JobResult:
        """Get a short-lived download URL for a completed job."""
        return JobResult.from_dict(self._request("GET", f"/v1/jobs/{_job_id(job)}/result"))

    def get_job_report(self, job: Union[str, Job]) -> JobReport:
        """Get a completed job's PDF/UA-1 report: the result for every accessibility requirement.

        Raises :class:`ConflictError` while the job is not completed, and :class:`NotFoundError`
        when the job has no PDF/UA-1 report.
        """
        return JobReport.from_dict(self._request("GET", f"/v1/jobs/{_job_id(job)}/report"))

    def submit_batch(
        self,
        items: Sequence[BatchItemInput],
        *,
        name: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: float = BATCH_SUBMIT_TIMEOUT,
    ) -> Batch:
        """Submit 1 to 100 uploaded files as one batch. Charges one credit per page.

        Each item is an upload ``key`` or a :class:`~pdftagger.models.BatchItem` (to set a
        filename or options). All or nothing: if any job is bad, this raises
        :class:`~pdftagger.exceptions.BadRequestError` with one entry in ``errors`` for each
        bad job, and nothing is charged; too few credits raises
        :class:`~pdftagger.exceptions.InsufficientCreditsError`.
        """
        jobs = [BatchItem(key=i) if isinstance(i, str) else i for i in items]
        payload: Dict[str, Any] = {"jobs": [j.to_payload() for j in jobs]}
        if name:
            payload["name"] = name
        headers: Dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return Batch.from_dict(
            self._request("POST", "/v1/batches", json=payload, headers=headers, timeout=timeout)
        )

    def get_batch(self, batch: Union[str, Batch]) -> Batch:
        """Fetch a batch's status, counts and jobs."""
        return Batch.from_dict(self._request("GET", f"/v1/batches/{_batch_id(batch)}"))

    # -- high-level helpers ------------------------------------------------------

    def tag_pdf(
        self,
        file: FileInput,
        *,
        ocr: bool = False,
        embed_fonts: bool = False,
        filename: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        wait: bool = True,
        poll_interval: float = 3.0,
        poll_timeout: Optional[float] = None,
    ) -> Job:
        """Upload, submit, and (by default) wait for a PDF to be tagged.

        Args:
            file: A path or open binary file for the PDF to tag.
            ocr: Force OCR on image-only pages.
            embed_fonts: Embed a non-embedded font where safe.
            filename: Name to record for the job (defaults to the file's name).
            idempotency_key: Make the submit safe to retry without double-charging.
            wait: If True, poll until the job finishes; if False, return the accepted job.
            poll_interval: Seconds between status checks while waiting.
            poll_timeout: Give up waiting after this many seconds. The default (``None``)
                waits until the job is terminal — the service guarantees a job reaches
                ``completed`` or ``failed`` within 24 hours. Set a bound if you need one.

        Returns:
            The :class:`~pdftagger.models.Job` — completed when ``wait`` is True.

        Raises:
            JobFailed: The job finished with a ``failed`` status.
            JobTimeout: ``wait`` is True and the job did not finish within ``poll_timeout``.
        """
        default_name = Path(file).name if isinstance(file, (str, Path)) else None
        upload = self.create_upload(filename=filename or default_name)
        self.upload_file(upload, file)
        job = self.submit_job(
            key=upload.key,
            ocr=ocr,
            embed_fonts=embed_fonts,
            filename=filename or default_name,
            idempotency_key=idempotency_key,
        )
        if not wait:
            return job
        return self.wait_for_job(job, poll_interval=poll_interval, poll_timeout=poll_timeout)

    def wait_for_job(
        self,
        job: Union[str, Job],
        *,
        poll_interval: float = 3.0,
        poll_timeout: Optional[float] = None,
    ) -> Job:
        """Poll a job until it is completed, raising on failure or timeout.

        ``poll_timeout=None`` (the default) waits until the job is terminal; the service
        guarantees that within 24 hours.
        """
        job_id = _job_id(job)
        deadline = time.monotonic() + poll_timeout if poll_timeout is not None else None

        while True:
            try:
                current = self.get_job(job_id)
            except RateLimitError as exc:
                time.sleep(exc.retry_after or poll_interval)
                continue

            if current.is_terminal:
                if current.status == "failed":
                    raise JobFailed(f"Job {current.id} failed", job=current)
                return current

            if deadline is not None and time.monotonic() >= deadline:
                raise JobTimeout(
                    f"Job {job_id} did not finish within {poll_timeout}s", job=current
                )

            time.sleep(poll_interval)

    def tag_pdfs(
        self,
        files: Sequence[FileInput],
        *,
        name: Optional[str] = None,
        ocr: bool = False,
        embed_fonts: bool = False,
        idempotency_key: Optional[str] = None,
        wait: bool = True,
        poll_interval: float = 5.0,
        poll_timeout: Optional[float] = None,
    ) -> Batch:
        """Upload many PDFs, submit them as one batch, and (by default) wait for all of them.

        Unlike :meth:`tag_pdf`, a failed job does not raise: a batch can finish with some
        jobs completed and some failed. Check :attr:`Batch.failed_jobs`, then save the rest
        with :meth:`download_batch_results`.

        Args:
            files: 1 to 100 paths or open binary files.
            name: A name for the batch (the API picks one if omitted).
            ocr: Force OCR on image-only pages, for every file.
            embed_fonts: Embed a non-embedded font where safe, for every file.
            idempotency_key: Make the submit safe to retry without double-charging.
            wait: If True, poll until every job has finished.
            poll_interval: Seconds between status checks while waiting.
            poll_timeout: Give up waiting after this many seconds (``None`` waits until done).
        """
        items: List[BatchItem] = []
        for file in files:
            filename = Path(file).name if isinstance(file, (str, Path)) else None
            upload = self.create_upload(filename=filename)
            self.upload_file(upload, file)
            items.append(BatchItem(key=upload.key, filename=filename, ocr=ocr, embed_fonts=embed_fonts))
        batch = self.submit_batch(items, name=name, idempotency_key=idempotency_key)
        if not wait:
            return batch
        return self.wait_for_batch(batch, poll_interval=poll_interval, poll_timeout=poll_timeout)

    def wait_for_batch(
        self,
        batch: Union[str, Batch],
        *,
        poll_interval: float = 5.0,
        poll_timeout: Optional[float] = None,
    ) -> Batch:
        """Poll a batch until every job has finished. Failed jobs do not raise.

        Raises:
            JobTimeout: The batch did not finish within ``poll_timeout`` seconds.
        """
        batch_id = _batch_id(batch)
        deadline = time.monotonic() + poll_timeout if poll_timeout is not None else None
        while True:
            try:
                current = self.get_batch(batch_id)
            except RateLimitError as exc:
                time.sleep(exc.retry_after or poll_interval)
                continue
            if current.is_terminal:
                return current
            if deadline is not None and time.monotonic() >= deadline:
                raise JobTimeout(f"Batch {batch_id} did not finish within {poll_timeout}s")
            time.sleep(poll_interval)

    def download_batch_results(self, batch: Union[str, Batch], dest_dir: Union[str, Path]) -> List[Path]:
        """Save every completed job's tagged PDF in ``dest_dir`` and return the paths.

        Files keep their uploaded names; a repeated name gets a number (``report (2).pdf``).
        Failed jobs are skipped.
        """
        current = batch if isinstance(batch, Batch) else self.get_batch(batch)
        folder = Path(dest_dir)
        folder.mkdir(parents=True, exist_ok=True)
        names = _unique_names([j.filename or f"{j.id}.pdf" for j in current.completed_jobs])
        return [
            self.download_result(job, folder / filename)  # type: ignore[misc]
            for job, filename in zip(current.completed_jobs, names)
        ]

    def download_result(
        self,
        job: Union[str, Job],
        dest: Optional[Union[str, Path]] = None,
    ) -> Union[bytes, Path]:
        """Download a completed job's tagged PDF.

        Returns the written :class:`~pathlib.Path` when ``dest`` is given, otherwise the
        PDF bytes.
        """
        return self._download(self.get_job_result(job).result_url, dest)

    def download_report(
        self,
        job: Union[str, Job],
        dest: Optional[Union[str, Path]] = None,
    ) -> Union[bytes, Path]:
        """Download a completed job's PDF/UA-1 report PDF.

        Returns the written :class:`~pathlib.Path` when ``dest`` is given, otherwise the
        PDF bytes. Raises :class:`NotFoundError` when the report PDF is no longer stored.
        """
        report = self.get_job_report(job)
        if not report.report_pdf_url:
            raise NotFoundError("The report PDF for this job is no longer stored.", status_code=404)
        return self._download(report.report_pdf_url, dest)

    def _download(self, url: str, dest: Optional[Union[str, Path]]) -> Union[bytes, Path]:
        try:
            response = self._http.get(url)
        except httpx.HTTPError as exc:
            raise APIError(f"Download failed: {exc}") from exc
        if not response.is_success:
            raise APIError(
                f"Download failed: HTTP {response.status_code}", status_code=response.status_code
            )

        if dest is None:
            return response.content
        path = Path(dest)
        path.write_bytes(response.content)
        return path


def _job_id(job: Union[str, Job]) -> str:
    return job.id if isinstance(job, Job) else job


def _batch_id(batch: Union[str, Batch]) -> str:
    return batch.id if isinstance(batch, Batch) else batch


def _unique_names(names: List[str]) -> List[str]:
    """Make file names unique, so two jobs with one name do not overwrite each other."""
    used = set()
    out = []
    for raw in names:
        name = Path(raw.replace("\\", "_")).name or "document.pdf"
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, "pdf"
        candidate, n = name, 2
        while candidate.lower() in used:
            candidate = f"{stem} ({n}).{ext}"
            n += 1
        used.add(candidate.lower())
        out.append(candidate)
    return out
