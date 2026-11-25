# AD-1114: The premise `rust_type_reach` needs a typed fact from the scan

Status: accepted. Amends AD-1047. Part of the path in the trait-dispatch design (first PR, no verdict change).

## Why

A PASS that reads module pairs printed "PASS under rust_type_reach" whenever the contract declared the premise
(`native/model/src/premises.rs`). It did so even when the scan ran with `rust_type_reach = false`, or when the
facts were unavailable or named no module of the scan. The receipt said more than the evidence.

## Decision

1. `archkeel_facts::type_reach` holds one typed definition of the producer output. `Descriptor` is the file that
   the producer writes for the Rust worker: `Unavailable { unavailable }` or `Produced` with one `Run` for each
   configuration. The hand-written JSON of `collect` and the hand-written reading of `native/rust` are gone.
2. `TypeReach` is the provenance fact: rustc text, target triple, driver SHA-256, `Cargo.lock` SHA-256, workspace
   members and the names of the configurations. `Produced::fact` derives it from the same record, so the
   descriptor and the fact cannot disagree.
3. The Rust worker puts the fact in `Facts::type_reach` only when the facts were verified and used. Used means that
   the filter was built and the facts name at least one module of the scan. The field is live only
   (`#[serde(skip)]`): a saved or wire reply carries none, like `scope_premise`. The private worker packet carries it.
4. The model checks the fact before any rule reads it (`settings::check_reach`, called by `admitted`). A fact
   without a rustc text, a target, two SHA-256 hashes, a member with a closing slash, only known configurations or
   the three fixed configurations is refused with `Refusal::TypeReach(<rule>)`. The refusal is typed and
   holds the whole run.
5. The premise label `rust_type_reach` is attached only when the contract declares the premise and the reply carries
   the fact. A declaration alone names nothing.
6. `Filter::excluded` stays the single negative decision. No gap, edge, rule result or exit code changes.

## Effect

The label text changes in two cases: the flag is off, or the facts were not used. Verdicts do not change. The
self-check keeps its label, because its scan uses the facts.

## Not done yet

- A saved reply never carries the fact, so a run on a saved reply names no premise.
- The fact does not say which pairs were excluded. A selected impl (a typed execution edge) is a later step.

## Checks

`native/rust/src/collect_reach_tests.rs` (the reply with, without and with unusable facts),
`native/model/src/settings_tests.rs` (each tampered part), `tests/test_cli_native_rust_type_reach.py`
(a declared premise without facts is not named).
