# AD-282 Keep plans and evidence out of the repository

**Status.** Accepted. The owner approved the removal on 2026-10-30.

**Decision.** The repository holds files that the product, a test or a reader needs. It does not
hold work records.
1. An agent plan or spec lives outside the repository, in a scratch folder or in the notes of the
   user. Do not add it under `docs/`.
2. Evidence for a release goes into the GitHub release or into the Git history. Do not add it
   under `docs/`.
3. The Git history is the archive. Restore a removed file from it when a real need comes back.

**Retired.** `docs/superpowers/` (67 plans and specs), `docs/evidence/` (16 measurement records),
two unused notes in `docs/architecture/`, `docs/release-1.0.0.md`, seven unused images in
`docs/assets/` and the release notes before 1.1.0.

**Reason.** No process read these files. They added 2 MB of text and images that readers must skip.

**Rejected.** Ignore the folders in `.gitignore`: five files in `docs/superpowers/` stay tracked.

**Limits.** The contracts cite five files in `docs/superpowers/` as provenance, and validation
reads each cited path. They stay until the contracts cite a decision record instead.

**Checks.** `tests/test_repository_hygiene.py` checks that the index lists each decision record.
No test blocks a new plan file: review does.
