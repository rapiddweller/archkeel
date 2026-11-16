# AD-600 Every section row kind is a typed variant and the frame states its constants

**Status.** Proposed. Part of #880. It closes the limits that AD-598 named.

**Decision.**
1. `native/core/src/section_rows.rs` types the rows of a section: the envelope (`id`,
   `evidence_class`, `area`, `title`, `subjects`, `evidence_ids`, `rule_ids`, `fact_ids`,
   `provenance`) and a closed, tagged `Body`: `kind` selects one of 19 variants and `data` is that
   variant's own struct (`deny_unknown_fields`). The frame holds `SectionRow`, so a row of an
   unknown kind, with a missing or a foreign field never reaches a frame. A core test applies
   `typed_rows` to the rows that the engine builds for every section and for the violations.
2. The schema generator joins the flattened envelope into each `oneOf` branch, so each row kind is
   one closed object in `schema/archkeel-core-frame-1.schema.json`.
3. The frame `protocol` word is a `const` of the schema.
4. The explain `version` and each budget are `const` values of the schema, written from the
   Rust constants (`explain.rs`). The shell reads the limits through `core_schema.budget` and keeps
   no copy; the checks of the list lengths stay in the shell.

**Limits.** `selector_role` of a selected construct is a text in the schema: the role words are an
enum of the contract crate, and the frame keeps them as text. The builders of the rows still write
JSON; the typed rows check them when the frame is made.
