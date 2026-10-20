# Expected review findings: `fixtures/M-review-workflow`

Revision 2, committed before run 2 (#600). Revision 1 (16d3e6b) graded run 1; S3 and S4
then failed because of fixture defects, so the fixture changed, not the earlier grading
([run 1](run-1.md)). A run passes a scenario when its decision matches and its rationale
cites the named evidence. Wording may differ. The contract is green
(12/12 PASS), so every finding below is review judgment, never a FAIL.

## Required of every run

- Traces `orders.api.place_order` through `checkout.service.place`, `pricing.price` and
  `storage.repository.save` to the selected backend, naming each layer's invariant.
- States review coverage per package and marks anything unreviewed.
- Each finding names a source location, impact, a delete/simplify/keep decision and UNKNOWNs.
- Keeps contract facts (PASS) separate from reviewer judgment.
- Names the symbols behind nonzero review-claim counts, or says where they are listed.

## S1 Green but generic leaf: `orders.common.util`

- Decision: **simplify**.
- Evidence: the responsibility "Shared helpers used across the service." names no purpose;
  only `slugify` has a caller (`orders.api`); `chunked` and `now_iso` have none.
- Expected: delete the unused helpers; give the remaining one a concrete purpose (SKU
  normalisation) or move it to its only caller. Not expected: splitting `common` further.

## S2 Unjustified public helper: `orders.checkout.rounding:round_cents`

- Decision: **simplify** (remove it from checkout's public API).
- Evidence: `orders.api.quote` recombines `pricing.price` and `round_cents`, the same
  "total in cents" knowledge that `checkout.service.place` owns. The observed import makes
  the contract green; it does not justify the publication.
- Expected: checkout owns one operation for the total (for example a quote next to
  `place`); rounding stays owner-local; `entry` stops requiring pricing and rounding.

## S3 Legitimate dynamic discovery: `orders.storage.backends.load_backend`

- Decision: **keep**.
- Evidence: a real caller (`storage.repository.save`, selected by `ORDERS_BACKEND`), the
  `Backend` protocol, a fail-fast check for unknown names, and the `cloud` backend's
  optional `boto3` extra (`pyproject.toml`): deployments without it must still start, so
  backends load only when selected. ArchKeel proves the literal loaders as dependencies.
- Not expected: static imports of every backend, or inventing an import to "justify" the
  backends. Acceptable side note: the `BACKEND` attribute of a loaded module is untyped
  until it meets the `Backend` annotation.

## S4 Cohesive larger package: `orders.pricing`

- Decision: **keep**.
- Evidence: ten direct modules exceed the review threshold of seven, but each holds one
  distinct pricing rule (clearance, bulk, coupon, VAT, small-order surcharge, shipping,
  currency) behind the `PriceStep` protocol, plus the line model, catalog and the ordered
  pipeline.
- Not expected: splitting by count, merging distinct rules into one module, `misc`/`utils`,
  or re-export barrels. Acceptable: a note that discount steps could form a subpackage if
  they grow.
