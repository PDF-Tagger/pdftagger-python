"""Tag a PDF, save the accessible result and print its PDF/UA-1 report.

Usage:
    export PDFTAGGER_API_KEY=sk_live_...
    python quickstart.py report.pdf
"""

import os
import sys

from pdftagger import JobFailed, JobTimeout, PdfTaggerClient


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python quickstart.py <file.pdf>", file=sys.stderr)
        return 2

    api_key = os.environ.get("PDFTAGGER_API_KEY")
    if not api_key:
        print("set PDFTAGGER_API_KEY first", file=sys.stderr)
        return 2

    source = sys.argv[1]
    out = source.rsplit(".", 1)[0] + ".tagged.pdf"

    with PdfTaggerClient(api_key=api_key) as client:
        account = client.get_account()
        print(f"Credits available: {account.credits_available}")
        try:
            job = client.tag_pdf(source, ocr=True)
        except JobFailed as exc:
            print(f"Job failed: {exc}", file=sys.stderr)
            return 1
        except JobTimeout as exc:
            print(f"Timed out waiting: {exc}", file=sys.stderr)
            return 1

        client.download_result(job, out)
        print(f"Tagged PDF saved to {out} (job {job.id}, {job.credits_used} credits)")

        report = client.get_job_report(job)
        print(f"{report.standard}: {report.summary}")
        for req in report.failed + report.needs_review:
            print(f"  {req.result}: {req.reference} {req.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
