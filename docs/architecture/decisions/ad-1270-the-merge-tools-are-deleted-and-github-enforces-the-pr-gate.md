# AD-1270: The merge tools are deleted and GitHub enforces the PR gate

Status: accepted. Owner decision 2026-11-27 (drift-gates audit, step F). Supersedes the merge-tool parts of AD-674,
AD-676 and AD-736.

## Why

`tools/merge_pr.py` decided MERGE, WAIT or REFUSE from the checks of a pull request, and `tools/merge_check.py`
(`make merge-check`) added local file checks. Branch protection of `main` now requires the check `PR gate` for
everyone, also for admins (`enforce_admins` true; `strict` false). The lead and the steward merge with the GitHub
merge after the PR gate and Codex. A second local decision table repeats what GitHub enforces, and it needs its own
tests (about 700 lines), the Make target and two entries in the lint lists.

## Decision

1. Deleted: `tools/merge_check.py`, `tools/merge_pr.py`, `make merge-check`, `tests/test_merge_check.py`,
   `tests/test_merge_pr.py`, their entries in `tests/areas.py` and in the ruff and mypy lists of the Makefile.
2. Merge only when the required check `PR gate` has passed (GitHub enforces it) and the review is done
   (CONTRIBUTING, merge rules 1 and 3).
3. The owner approves the deletion of a whole feature in the PR text. There is no label `deletion-approved`.

## What still covers each removed check

| Removed | Real defect | Still covered by |
|---|---|---|
| Required check red, pending or missing | A merge on a red gate | Branch protection: the required check `PR gate`, also for admins. |
| Conflicts, merge state `UNKNOWN` | A merge that does not land | GitHub does not merge a conflicting PR; `ready.sh` waits on the merge state. |
| Local file list against the GitHub file list | A moved file read as a deletion | None; a moved file shows in the PR diff and the review. |
| `deletion_unapproved` (a deleted file or more than 300 net lines, label) | A whole feature deleted without the owner | The owner's approval in the PR text; the lead checks it. None by tooling: owner decision. |
| Empty landing (merge produced no change) | A merge that lands nothing | The merge commit on `main` and main CI. |

## Not done yet

The merge-tree check of the lead is a manual step and stays outside the repository.
