"""Verify PDF Tagger webhook deliveries.

Every delivery carries an ``X-PDFTagger-Signature`` header of the form
``t=<unixSeconds>,v1=<hex-hmac>``, where the HMAC is SHA-256 over ``"<t>.<rawBody>"``
keyed by the endpoint secret (``whsec_…``). :func:`verify_signature` recomputes the HMAC
over the exact bytes you received, compares it in constant time, and rejects a stale
timestamp (replay). This mirrors the server's ``signWebhook`` implementation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Dict, Optional, Union

from .exceptions import WebhookVerificationError
from .models import WebhookEvent

#: Header the server sends the signature in.
SIGNATURE_HEADER = "X-PDFTagger-Signature"
#: Default replay window, in seconds.
DEFAULT_TOLERANCE_SECONDS = 300


def _parse_signature_header(header: str) -> Dict[str, str]:
    parts: Dict[str, str] = {}
    for item in header.split(","):
        item = item.strip()
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key.strip()] = value.strip()
    return parts


def verify_signature(
    payload: Union[bytes, bytearray, str],
    header: Optional[str],
    secret: str,
    *,
    tolerance: Optional[int] = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[int] = None,
) -> WebhookEvent:
    """Verify a webhook signature and return the parsed event.

    Args:
        payload: The **raw** request body, exactly as received (bytes are preferred; a
            str is encoded as UTF-8). Do not re-serialize a parsed JSON object — a
            different byte layout will not match the signature.
        header: The ``X-PDFTagger-Signature`` header value.
        secret: The endpoint signing secret (``whsec_…``).
        tolerance: Max allowed difference between the signed timestamp and now, in
            seconds. Pass ``None`` to skip the replay check.
        now: Current unix time, for testing. Defaults to :func:`time.time`.

    Returns:
        The verified :class:`~pdftagger.models.WebhookEvent`.

    Raises:
        WebhookVerificationError: If the header is missing or malformed, the signature
            does not match, the timestamp is outside ``tolerance``, or the body is not
            valid JSON.
    """
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)

    if not header:
        raise WebhookVerificationError("Missing signature header")

    parts = _parse_signature_header(header)
    timestamp = parts.get("t")
    provided = parts.get("v1")
    if not timestamp or not provided:
        raise WebhookVerificationError("Malformed signature header")

    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("Invalid timestamp in signature header") from exc

    signed = f"{timestamp_int}.".encode("utf-8") + payload_bytes
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, provided):
        raise WebhookVerificationError("Signature mismatch")

    if tolerance is not None:
        current = int(now if now is not None else time.time())
        if abs(current - timestamp_int) > tolerance:
            raise WebhookVerificationError("Timestamp outside tolerance (possible replay)")

    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except ValueError as exc:
        raise WebhookVerificationError(f"Payload is not valid JSON: {exc}") from exc

    return WebhookEvent.from_dict(data)
