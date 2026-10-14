"""Cross-language proof: a signature produced by the server's Node algorithm verifies
in the Python SDK. The Node reference (_sign_reference.mjs) is copied verbatim from the
PDF Tagger server's signing function, so this exercises the real server scheme end to end.

Skips cleanly when Node is not installed.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from pdftagger import WebhookVerificationError, verify_signature

SECRET = "whsec_cross_lang_secret"
REF = Path(__file__).parent / "_sign_reference.mjs"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def node_sign(secret: str, timestamp: int, body: str) -> str:
    out = subprocess.run(
        ["node", str(REF), secret, str(timestamp), body],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def test_node_signed_payload_verifies_in_python():
    ts = int(time.time())
    body = json.dumps(
        {"id": "evt_x", "type": "job.completed", "data": {"job": {"id": "job_x", "status": "completed"}}}
    )
    header = node_sign(SECRET, ts, body)

    event = verify_signature(body, header, SECRET)
    assert event.job is not None
    assert event.job.id == "job_x"


def test_node_signature_with_wrong_secret_fails_in_python():
    ts = int(time.time())
    body = json.dumps({"id": "evt_y", "type": "job.failed"})
    header = node_sign(SECRET, ts, body)

    with pytest.raises(WebhookVerificationError):
        verify_signature(body, header, "whsec_not_the_secret")


def test_node_signature_survives_unicode_body():
    # UTF-8 handling must match between runtimes.
    ts = int(time.time())
    body = json.dumps({"id": "evt_z", "type": "job.completed", "note": "café — résumé 日本語"})
    header = node_sign(SECRET, ts, body)

    event = verify_signature(body, header, SECRET)
    assert event.id == "evt_z"
