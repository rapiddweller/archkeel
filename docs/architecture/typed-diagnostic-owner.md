# Owned diagnostic values

The `ir.diagnostics` owner contains the existing 11 diagnostic kinds, 32 codes, immutable diagnostics, source locations and diagnostic exception. `ir.model` explicitly reexports the same classes. Valid wire spellings, legacy string construction, errors and frozen behavior remain supported. Actual producers and decisions use the canonical enum values.

Existing public names in `check.report`, `render.html` and `render.terminal` explicitly reexport the canonical owner directly. This preserves their API without adding a second facade hop. Source-backed native controls retain those actual imports; reverting only the three import fixes reproduces the five unresolved routes.

The diagnostic owner alone has a whole-module native string-control guard. Twenty independently authored Target entities describe the enum identities, DTO fields and exception signature. Source mutations widen the kind/code/exception fields and exception constructor parameter/return while keeping that intent fixed; raw equality, membership, protocol-key membership, match and Final-string dispatch are rejected.

Against integrated Graph+Version `5933ffbbfd588ac96e36748de937cb1f6e739655`, native validation retains 918 unresolved calls and 58 UNKNOWN positions, with no new type-position IDs, violations, diagnostics or graph failures. The 16 existing Result positions proceed past `diagnostics.kind` to the pre-existing `coverage.failures.data.entries` shape; they remain UNKNOWN. Evidence compares individual positions and call-site multiplicities, including partial calls and the two unchanged call bodies relocated from model to diagnostics.

The production change adds 65 net lines across the necessary producers and consumers; `ir.model` itself shrinks by 86. There is no generic conversion framework or copied observation Target. Historical JSON schemas are unchanged. Result, comparison, amendment and command controls remain separate pending #542 increments; no whole-model guarantee is made.
