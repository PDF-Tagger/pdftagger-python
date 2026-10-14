"""Receive and verify PDF Tagger webhooks with Flask.

Usage:
    export PDFTAGGER_WEBHOOK_SECRET=whsec_...
    pip install flask
    flask --app webhook_flask run
"""

import os

from flask import Flask, request

from pdftagger import WebhookVerificationError, verify_signature
from pdftagger.webhooks import SIGNATURE_HEADER

app = Flask(__name__)
SECRET = os.environ["PDFTAGGER_WEBHOOK_SECRET"]

# Remember handled events — deliveries can arrive more than once.
_seen: set[str] = set()


@app.post("/webhooks/pdftagger")
def receive():
    try:
        event = verify_signature(
            payload=request.get_data(),  # raw bytes — do NOT use request.json here
            header=request.headers.get(SIGNATURE_HEADER),
            secret=SECRET,
        )
    except WebhookVerificationError:
        return "", 400

    if event.id in _seen:
        return "", 200  # already handled: a retried delivery keeps the same event id
    _seen.add(event.id)

    if event.type == "job.completed":
        print(f"Job {event.job.id} completed — fetch its result URL to download.")
    elif event.type == "job.failed":
        print(f"Job {event.job.id} failed: {event.job.error_message}")
    elif event.type == "batch.completed":
        b = event.batch
        print(f"Batch {b.id} finished: {b.completed} completed, {b.failed} failed.")

    return "", 200
