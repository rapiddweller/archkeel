# AD-141 GitHub events are bounded observations

Collect PR/base/head metadata and hashed GitHub Events through
`gh`. Validate provider IDs, refs, hashes, timestamps and pagination; malformed or
ambiguous evidence yields UNKNOWN. The job reports evidence without changing gates.

Recent events cannot prove first publication or absence of earlier pushes.
Partial history cannot become complete host proof; commit dates
and PR updates are insufficient. A missing accepted lock stays a separate diagnostic.
[AD-143](ad-143-initial-pr-head-proves-scoped-order.md) provides a scoped alternative.

[Collector proof](../../../tests/test_github_pr_report.py).
