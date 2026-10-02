# AD-141 GitHub events are bounded observations

## Problem

GitHub PR CI has no accepted main lock or complete first-publication history.
Two recent push timestamps cannot certify the M → B → E → H protocol.

## Decision

`tools/github_pr_report.py` uses configured `gh` to save PR metadata and paginated
head-repository events, bind the exact run base/head and hash the raw responses.
It validates push repository IDs, event IDs, SHA-40 heads/before values, refs and
timezone-aware host timestamps. Duplicate event IDs are ambiguous pagination.
Existing `unknown_result` and check HTML emit a usable exit-2 report even when the
accepted lock is missing. The separate CI job is report-only; gate policy is unchanged.

| Input | Result |
|---|---|
| Exact PR binding and two ordered pushes | UNKNOWN: first publication unproven |
| Reversed pushes, missing history or 300-event cap | UNKNOWN |
| Changed base/head, malformed response or duplicated ID | UNKNOWN with diagnostic |
| Missing/invalid accepted main lock | Separate diagnostic; no replacement lock |

## Rejected

Commit author/committer dates, PR `updated_at` and removed `Commit.pushedDate` are
not publication proof. Partial Events pages must never become authenticated
complete `HostRecord` inputs. No host enum or alternate result model is added.

## Limit

GitHub Events retains at most 300 events for 30 days and can lag 30 seconds to
6 hours. Even fewer events do not prove an earlier push absent. The collector
cannot certify host order or compare an unavailable accepted baseline.
Full #216 still needs an accepted main lock and a decided trusted collection source.

## Checks

`tests/test_github_pr_report.py`; `make demo-github` reuses the local Git A/B/C
protocol and adds simulated GitHub order, missing/ambiguous history and digest controls.
