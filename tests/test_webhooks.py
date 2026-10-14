"""Unit tests for webhook signature verification (pure, no network)."""

import hashlib
import hmac
import json
import time

import pytest

from pdftagger import WebhookVerificationError, verify_signature

SECRET = "whsec_test_secret"
BODY = json.dumps(
    {"id": "evt_1", "type": "job.completed", "created": 1, "data": {"job": {"id": "job_1", "status": "completed"}}}
).encode("utf-8")


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """Reproduce the server's signWebhook() for test inputs."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def test_valid_signature_returns_event():
    ts = int(time.time())
    event = verify_signature(BODY, sign(SECRET, ts, BODY), SECRET)
    assert event.type == "job.completed"
    assert event.job is not None
    assert event.job.id == "job_1"
    assert event.job.succeeded


def test_accepts_str_payload():
    ts = int(time.time())
    event = verify_signature(BODY.decode(), sign(SECRET, ts, BODY), SECRET)
    assert event.id == "evt_1"


def test_missing_header_rejected():
    with pytest.raises(WebhookVerificationError):
        verify_signature(BODY, None, SECRET)


def test_malformed_header_rejected():
    with pytest.raises(WebhookVerificationError):
        verify_signature(BODY, "not-a-signature", SECRET)


def test_bad_signature_rejected():
    ts = int(time.time())
    header = f"t={ts},v1=" + "0" * 64
    with pytest.raises(WebhookVerificationError):
        verify_signature(BODY, header, SECRET)


def test_tampered_body_rejected():
    ts = int(time.time())
    header = sign(SECRET, ts, BODY)
    tampered = BODY.replace(b"completed", b"failed")
    with pytest.raises(WebhookVerificationError):
        verify_signature(tampered, header, SECRET)


def test_wrong_secret_rejected():
    ts = int(time.time())
    header = sign(SECRET, ts, BODY)
    with pytest.raises(WebhookVerificationError):
        verify_signature(BODY, header, "whsec_other")


def test_stale_timestamp_rejected():
    ts = int(time.time()) - 10_000
    header = sign(SECRET, ts, BODY)
    with pytest.raises(WebhookVerificationError):
        verify_signature(BODY, header, SECRET, tolerance=300)


def test_stale_timestamp_allowed_when_tolerance_none():
    ts = int(time.time()) - 10_000
    header = sign(SECRET, ts, BODY)
    event = verify_signature(BODY, header, SECRET, tolerance=None)
    assert event.type == "job.completed"


def test_now_override_controls_tolerance():
    ts = 1_000_000
    header = sign(SECRET, ts, BODY)
    # now exactly at the edge of the window passes; just past it fails.
    assert verify_signature(BODY, header, SECRET, tolerance=300, now=ts + 300)
    with pytest.raises(WebhookVerificationError):
        verify_signature(BODY, header, SECRET, tolerance=300, now=ts + 301)
