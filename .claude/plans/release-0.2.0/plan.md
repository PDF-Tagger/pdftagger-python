# Plan: pdftagger 0.2.0

- [ ] `JobReport` and `Requirement` models; export them.
- [ ] `get_job_report()` and `download_report()` on the client.
- [ ] Tests: parsing, the two methods, the error cases, a report with no PDF.
- [ ] README: a "PDF/UA-1 report" section. `examples/quickstart.py` prints the summary.
- [ ] Version 0.2.0 in `_version.py`.

## Verification (Phase 3.5 gate)
- [ ] `pytest`: paste the counts.
- [ ] Real end to end against the deployed API (after the web PR merges): tag a PDF, read the report, download the
      report PDF.
- [ ] After Rachel publishes the GitHub release: the "Publish to PyPI" run passes and the PyPI page has no banner.
