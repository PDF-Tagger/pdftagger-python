# Scope: Release pdftagger 0.1.2

## Problem
PyPI shows a **"Change of provenance"** warning on pdftagger 0.1.1, and because 0.1.1 is the
latest release, the warning appears as a banner on the main project page
(pypi.org/project/pdftagger). 0.1.0 was published from `rachel-ackeret/pdftagger-python`;
0.1.1 was published from `PDF-Tagger/pdftagger-python` after the repo moved to the org. PyPI
flags that change of source repo and workflow URL.

## Why it matters
The banner says the release files "may have been compromised". For an SDK that new users find
through PyPI, it's a trust problem on the very first page they see, even though the change was
intentional.

## How PyPI decides (researched in pypi/warehouse source)
- `Release.comparison_provenance_release` / `_provenance_comparison` in
  `warehouse/packaging/models.py`: a release is compared against the **most recent earlier
  release with attestations, created within the previous 14 days**
  (`PROVENANCE_COMPARISON_WINDOW_DAYS = 14`). There is **no yanked filter**.
- `ProvenanceStatus.states` in `warehouse/attestations/models.py`: `changed-provenance` is
  set when any publisher source or workflow is added or removed compared with that release.
  Sources compare by `(kind, repository)` and workflows by `(kind, repository, workflow file)`.
  The workflow permalink (which embeds the commit SHA) is `compare=False`, so a new commit
  does not count as a change.
- `templates/includes/packaging/project-status.html`: the banner is drawn for the release being
  viewed; the bare project page shows the latest release.

Consequences:
- **Yanking 0.1.0 does not help.** It still counts as the comparison release.
- **Publishing 0.1.2 from the org repo clears the main page.** 0.1.2 is compared with 0.1.1
  (same repo, same `publish.yml`, so nothing changes), or with nothing if it lands after
  2026-10-28T21:58Z (14 days after 0.1.1). Either way, 0.1.2 has no warning.
- **The warning on 0.1.1's own page and its Release-history entry is permanent.** Only deleting
  0.1.0 would clear it, which is irreversible and burns the version number. Not doing that.

## Constraints
- Release only through the existing trusted-publishing flow (`RELEASING.md`): bump
  `src/pdftagger/_version.py`, merge, publish a GitHub release tagged `v0.1.2`.
- No code changes are required. Rachel may add changes to this PR before release.

## Relevant files & systems
- `src/pdftagger/_version.py`: the single version source (hatch reads it).
- `.github/workflows/publish.yml`: the trusted publisher identity (must stay unchanged so 0.1.2
  matches 0.1.1).
- PyPI project settings → Publishing: should list only `PDF-Tagger/pdftagger-python`,
  `publish.yml`, environment `pypi`.
- Local `origin` remote still points to `rachel-ackeret/pdftagger-python`. GitHub redirects it;
  Rachel can repoint it with
  `git remote set-url origin https://github.com/PDF-Tagger/pdftagger-python.git`.

## Out of scope
- Deleting or yanking 0.1.0.
- Renaming or moving `publish.yml`: its path is part of the publisher identity, so a rename
  would trigger the same warning again on 0.1.2.
