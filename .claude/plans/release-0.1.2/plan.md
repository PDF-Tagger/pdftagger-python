# Plan: Release pdftagger 0.1.2

- [ ] Step 1: Rachel decides whether any other changes ship in 0.1.2 (add them to this PR).
- [ ] Step 2: Bump `src/pdftagger/_version.py` to `0.1.2`.
- [ ] Step 3: Run the full test suite and `python -m build` + `twine check` locally.
- [ ] Step 4: Rachel (PyPI UI): confirm Manage → Publishing lists only
      `PDF-Tagger/pdftagger-python` / `publish.yml` / `pypi`; remove any `rachel-ackeret` publisher.
- [ ] Step 5: Cleanup (Phase 4): delete `plan.md` and `scope.md`, keep the durable bits by adding
      a short "Provenance" note to `RELEASING.md` (keep the trusted publisher identity stable;
      a repo/workflow move triggers PyPI's "Change of provenance" warning on the next release).
- [ ] Step 6: Rachel merges, then publishes a GitHub release `v0.1.2` with the notes below.
- [ ] Step 7: Confirm the publish run succeeded and check PyPI's security info for 0.1.2.

## Draft GitHub release notes (v0.1.2)

> Published from github.com/PDF-Tagger/pdftagger-python with PyPI trusted publishing.
>
> PyPI shows a "Change of provenance" notice on 0.1.1. That reflects the intentional move of
> this repository from `rachel-ackeret/pdftagger-python` to the PDF-Tagger organization in
> 0.1.1. Releases from 0.1.1 on are published from this repository by
> `.github/workflows/publish.yml`.
>
> No API changes.

(Update the last line if other changes are added to this release.)

## Verification (Phase 3.5 gate, must be filled with REAL evidence before "ready")
- [ ] Repro (BEFORE): PyPI shows `changed-provenance` for 0.1.1 (Rachel's screenshot
      of the 0.1.1 Security tab, plus the publisher identities from PyPI's integrity API for 0.1.0
      and 0.1.1) — paste output
- [ ] Built artifacts report version 0.1.2 and pass `twine check` — paste output
- [ ] Full `python -m pytest -q` output — paste output
- [ ] AFTER (post-release, done by Claude once Rachel publishes): the integrity API shows 0.1.2
      with the same publisher as 0.1.1, and pypi.org/project/pdftagger/ shows no
      "Change of provenance" banner — paste output
