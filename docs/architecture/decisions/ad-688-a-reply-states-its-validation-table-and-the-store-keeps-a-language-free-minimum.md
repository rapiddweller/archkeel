# AD-688 A reply states its validation table, and the store keeps a language-free minimum

**Status.** Accepted (owner approval of the proposal "store language-neutral", 2026-11-16). Part of
#880, issue #1384. It amends AD-346 (the store validates a reply once), AD-378 (registered sets),
AD-388 (pinned standard library) and AD-668 (a neutral crate names no language).

**Reason.** `store` validated a reply by its language: 21 sites named `Profile`, and `store.python`
and `store.dart` held the checks of one language each. AD-668 made these sites visible as 27 FAIL
rows of the self-check. The tables that the store read by profile belong to the collectors:
the registered capability sets, what an interface statement needs, the standard library and the
SDK libraries. The store must check each reply with the same strength, without a language branch.

**Decision.**
1. Protocol 11. Each native collector writes the 11.0.0 reply for each request version. Its facts
   carry one new block `validation`, filled by the collector from its own table:
   - `registered`: the capability sets of the collector. Each set has the sections and the
     resolution features that the reply must state, the ones that it may state in addition, and its
     construct capabilities in order, each with the statuses that it may have.
   - `interface`: what an interface statement of the collector needs: `nothing`, `unsupported`, or
     one resolution feature (the statement holds exactly when the reply states the feature).
   - `standard_library`: the owner key of the pinned standard library in `archkeel-facts`
     (`standard_library.txt`), the profile or the profile and the minor version of the target after
     `@`. The part before `@` also names the pinned SDK libraries (`sdk_libraries.txt`).
   The schema is regenerated as `native/facts/schema/archkeel-facts-11.schema.json`.
2. The block can only add checks. The store keeps a language-free minimum that no block lowers:
   - each feature that a registered set or the interface need names is a feature whose claims the
     store checks;
   - the family of the standard library key is the adapter name of the reply, and a versioned key
     is the minor version of the runtime of the reply;
   - a symbol statement needs a feature that writes the symbol of each import (`script-globals-v1`,
     `import-routes-v1`, `rust-item-routes-v1`);
   - a script effect needs the feature `script-globals-v1`;
   - a record may cite the evidence of another file only when the reply lists that file as owned by
     the module of the record (`owned_files`, a Dart part, AD-468), and each parsed file is a module
     or an owned file.
   Then the capabilities of the reply must be exactly one registered set of the block, and an
   interface statement must agree with the need of the block.
3. The transition. A reply of protocol 8, 9 or 10 has no block. The store reads it with its
   profile checks, and `Facts::standard_library_key` gives its key from the profile and the runtime.
   A reply of protocol 11 without a block, or an older reply with a block, is refused.

**Why it is sound.** A wrong block cannot widen the store. It can name only features that the
store checks, only the pinned list of its own adapter and runtime, and only restrictions on top of
the minimum. A block that requires fewer features than the reply states admits no set, so the reply
is refused. A block that drops a feature that a statement needs leaves the statement without its
feature, so the minimum refuses the reply (plant: `validation_tests.rs`,
`a_block_with_fewer_required_features_cannot_lower_the_symbol_rule`). The tables of the collectors
are the tables that the store had: no set that the store refused is in a block. The Rust table
admits no construct capability, which the store did not check before; this is stricter.
The part evidence and the parsed-file count now come from `owned_files`, which only a linked
collector writes, and not from the profile. A wire reply of the Dart profile with a part is now
refused; no such reply exists.

**Measured.** Native self-check, step 1 (this record): 27 -> 17 violations of
`NATIVE-NEUTRAL-STORE-NO-PROFILE` and `NATIVE-NEUTRAL-CORE-NO-PROFILE` together with the module
rules (`store.standard`, `store.bindings`, `store.records` and one site of `store.validate` name no
`Profile`).

**Rejected.**
- A `part_evidence` and an `effects` flag in the block. A flag that a reply sets would relax the
  store. The owned files and the script feature are facts of the reply that the store checks.
- The standard library names in the block. A reply could then widen the list; the block names only
  the key of a pinned table.
- A copy of the collector tables in `archkeel-facts` for the old replies. The store keeps its
  profile checks for them during the transition, so no table is written twice.

**Tests.** `native/store/src/validation_tests.rs` (the block and its minimum, both front doors),
`native/store/src/standard.rs` (the key tables), `native/collect` tests (each linked collector
reply passes the profile checks and its own block).
