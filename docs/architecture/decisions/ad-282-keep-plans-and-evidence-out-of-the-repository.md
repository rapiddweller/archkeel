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
two unused notes in `docs/architecture/`, `docs/release-1.0.0.md`, eight unused images in
`docs/assets/` and the release notes before 1.1.0.

**Reason.** No process read these files. They added 2 MB of text and images that readers must skip.

**Rejected.** Ignore the folders in `.gitignore`: an ignored plan leaves `git status` and review
without a sign, and a cleaned worktree loses it.

**Limits.** The contracts cite five files in `docs/superpowers/` as provenance, and validation
reads each cited path. They stay until the contracts cite a decision record instead.

**Checks.** `test_plans_and_evidence_stay_out_of_the_repository` fails when a tracked file under
`docs/superpowers/` or `docs/evidence/` is not cited by a contract. `test_decision_index_matches_decision_files`
pins the index row.
