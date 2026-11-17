# AD-676 The merge tool merges only on green and never with admin

**Status.** Accepted. Owner decision of 2026-11-16. Part of #880. Follows AD-674.

**Reason.** The merge helper in `/tmp` used `gh pr merge --admin`, so a red required check did not block, and a broken worktree landed three empty squash commits (#1337, #1338, #1340).

**Decision.** `tools/merge_pr.py <number>` is the one way to merge. It refuses unless the pull request is open, not a draft, mergeable and not behind its base, and each required check of the base branch (the branch protection list, `PR gate` by default) has the conclusion `success` on the head commit. A missing, skipped, pending, neutral or cancelled check refuses. It merges with `--squash --match-head-commit <head>` and has no `--admin` and no `--no-verify`. After the merge it reads the merge commit: a commit that changes no file while the pull request changed files is an error (exit 2).

**Rejected.** A shell script in `/tmp` (not reviewed, no test); trusting `gh pr merge` alone (it lands an empty squash without a word).

**Limit.** The tool trusts the check names that GitHub reports. The branch protection (required check `PR gate`, no bypass for admins) is the second lock.

**Tests.** `tests/test_merge_pr.py`.
