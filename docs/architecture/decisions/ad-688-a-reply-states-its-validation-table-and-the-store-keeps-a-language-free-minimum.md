# AD-688 A reply states its validation table, and the store keeps a language-free minimum

**Status.** Accepted (owner approval of the proposal "store language-neutral", 2026-11-16). Part of
#880, issue #1384. It amends AD-346, AD-378 (registered sets), AD-388 (pinned standard library)
and AD-668 (a neutral crate names no language).

**Reason.** `store` validated a reply by its language: 21 sites named `Profile`, and `store.python`
and `store.dart` held the checks of one language each (27 FAIL rows of AD-668). The tables that the
store read by profile belong to the collectors.

**Decision.**
1. Protocol 11. Each native collector writes the 11.0.0 reply. Its facts carry the block
   `validation`, filled from the table of the collector: `registered` (the capability sets: the
   sections and features that a reply must state and may state, and the construct capabilities in
   order with their allowed statuses); `interface` (`nothing`, `unsupported`, or the one feature
   with which an interface statement holds); `standard_library` (the owner key of the pinned list in
   `archkeel-facts`, the profile or the profile and the minor of the target after `@`; the part
   before `@` names the pinned SDK libraries). Schema: `archkeel-facts-11.schema.json`.
2. The block can only add checks. The store keeps a minimum that no block lowers: a feature that a
   block names is one whose claims the store checks; a versioned key names the minor of the runtime;
   a symbol statement needs a feature that writes the symbol of each import; a script effect needs
   `script-globals-v1`; a record cites the evidence of another file only when the reply owns that
   file to the module of the record (`owned_files`), and each owned file is a selected non-module
   file with one owner module; each parsed file is a module or an owned file. Then the capabilities
   must be exactly one registered set, and an interface statement must agree with the block.
3. The core trusts a reply only when its key names the list of its adapter, besides the profile,
   the adapter and the code digest. The store makes no producer claim (AD-406 review F2).
4. Transition. Step 1 read the 8, 9 and 10 replies with the old profile checks. Step 2 ends it: the
   decode refuses another protocol and a reply without a block.
5. The checks of one language (step 3) live in their collector: `archkeel_python_collector::check`
   (builtin and external targets against the pinned list of the key, import statements) and
   `archkeel_dart_collector::check` (Dart URI targets, import and export statements, each selected
   file accounted for); both require the coverage gaps to be the unknowns, each once
   (`archkeel_facts::surveys`), which another collector need not hold. `archkeel_collect::check` calls the one of the profile of the reply after
   the store, for the scan and for the byte door of the harness; the core names no profile.
   The rules `NATIVE-NEUTRAL-STORE-NO-PYTHON-MODULE` and `-NO-DART-MODULE` of AD-668 are removed
   with the two modules that they target (a rule that selects no module holds the whole run).
   `tests/test_native_neutral_crates.py` still requires a rule for each language module of a
   neutral crate, and `NATIVE-NEUTRAL-STORE-NO-PROFILE` stays.

**Why it is sound.** A block cannot widen the store: it names only features that the store checks
and only the key of a pinned list, and it only restricts the minimum. A block that requires fewer
features than the reply states admits no set; a block that drops the feature of a statement leaves
the statement without its feature, and the minimum refuses the reply (plant:
`a_block_with_fewer_required_features_cannot_lower_the_symbol_rule`). The tables are the store
tables of before, with two stricter points: the Rust table admits no construct capability, and the
TypeScript table drops the set `static-imports` of the 4.0.1 Python collector, which the native
collector never writes. Part evidence and the parsed count now come from `owned_files`, which only
a linked collector writes; a wire reply of the Dart profile with a part is refused (none exists).

**Measured.** Visible violations of the four rules of AD-668 in the native self-check:
- step 1: 27 -> 18 (`store.standard`, `store.bindings`, `store.records` name no `Profile`);
- step 2: 18 -> 9 (`store.registered` deleted; `store.python` keeps only the survey checks);
- step 3: 9 -> 0 (`store.python` and `store.dart` deleted; `core.scan` names no `Profile`);
  the native self-check is 91 PASS, 1 FAIL (`NATIVE-PUBLIC-HAS-A-USER`, #1402), 0 UNKNOWN.

**Rejected.**
- A `part_evidence` or an `effects` flag in the block: a flag that a reply sets relaxes the store.
- The standard library names in the block: a reply could widen the list.
- A copy of the collector tables for old replies: no table is written twice.

**Tests.** `native/store/src/validation_tests.rs` (the minimum, both front doors),
`registered_tests.rs` (the TypeScript table on the golden replies, which carry
`tests/golden/typescript/validation.json`, checked equal to the table by the collector),
`standard.rs`, `native/collect/src/{python,dart,rust}_tests.rs` (each table on a real reply),
`native/core/src/check_tests.rs` (the key in the trust), `native/python/src/claims.rs`,
`native/dart/src/import_survey/claims.rs`.
