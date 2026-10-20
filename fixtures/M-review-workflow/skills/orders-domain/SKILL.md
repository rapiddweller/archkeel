---
name: orders-domain
description: Use with the archkeel skill when reviewing or changing the orders service; supplies its domain invariants only.
---

# Orders domain invariants

Review method: follow the `archkeel` skill's physical structure review. This skill adds only
what is specific to this service; it does not repeat that process.

- Money: a total is whole cents of one currency; a receipt names the currency it was charged in.
- Rounding: totals round once, at checkout, half away from zero.
- Receipts are immutable and every placed order persists exactly one, never overwriting another.
- Entry points validate SKU, region and quantity before any pricing runs.
- A backend that needs an optional extra (`cloud` needs boto3) must not be imported unless selected.
- Region rules (tax, shipping fee, currency) for one region change together.
