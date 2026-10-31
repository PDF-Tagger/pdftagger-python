# Releasing

PyPI publishing is automatic: publishing a GitHub release runs `.github/workflows/publish.yml`,
which builds the package and uploads it with PyPI trusted publishing (no token).

1. Set the new version in `src/pdftagger/_version.py` and merge it to `main`.
2. On GitHub, create a release with the tag `v<version>` (for example `v0.1.0`) and publish it.
3. Check the "Publish to PyPI" workflow run, then `pip install pdftagger==<version>`.

One-time setup (already done once it has been published):

- On PyPI, add a trusted publisher for the project `pdftagger`: owner `PDF-Tagger`,
  repository `pdftagger-python`, workflow `publish.yml`, environment `pypi`. Before the first
  release this is a "pending publisher" (Account settings → Publishing).
- On GitHub, create the environment `pypi` (Settings → Environments).

## The PyPI provenance banner

PyPI compares each release with the latest earlier release that has attestations and was made within 14 days. It
shows a "Change of provenance" warning when the publishing repository or workflow changed. 0.1.1 has that warning
because 0.1.0 came from `rachel-ackeret/pdftagger-python` and 0.1.1 from `PDF-Tagger/pdftagger-python`. Every later
release from this repository and `publish.yml` has no warning, so the project page is clean from 0.2.0 on. Keep the
repository and the workflow file name the same; a change brings the warning back for one release. Do not delete
0.1.0 to clear 0.1.1's own page: deletion is permanent and burns the version number.

## Releases that need an API change

Publish a release only after every API endpoint it calls is live on api.pdf-tagger.com. 0.2.0 calls
`GET /v1/jobs/{id}/report`.
