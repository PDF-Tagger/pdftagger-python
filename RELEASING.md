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
