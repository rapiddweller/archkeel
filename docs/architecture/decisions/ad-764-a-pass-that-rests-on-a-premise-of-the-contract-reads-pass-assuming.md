# AD-764: A PASS that rests on a premise of the contract reads "PASS assuming"

Status: accepted (lead order, 2026-11-17). Fixes #1549, gives #1538 its seam. Part of #880.
Generalizes AD-664.

1. Problem. AD-664 made a PASS under a declared door reach read "PASS assuming the declared reach
   of N doors". An `unused_public` rule skips each item that its `external_users` list names
   (AD-670, AD-746), and such a rule read as a plain PASS, although the entry is a claim of the
   contract about code outside the scan, not a proof. A third claim (#1538: no code changes the
   standard library) had no place in the contract at all.
2. A premise is a statement of the contract about what the scan cannot see, on which a PASS
   rests. Three kinds exist, with one seam:
   - the declared reach of a door site (`declarations.door_reach`, AD-664);
   - a stated external user of a public item (`external_users`); it is a premise of a rule only
     when no other component is proven to use the item, so an entry for a used item is none;
   - a premise that the contract declares by name (`declarations.premises`, contract 3.17.0):
     `{"id", "name", "rationale", "provenance"}`. The names are `PremiseName` of the contract
     crate, each with its words; the first is `standard_library_unchanged` ("an unchanged
     standard library"). No rule rests on it yet. An unknown name refuses the contract.
   Policy entries on facts that the scan sees are no premises: `allowed_sources`,
   `allowed_type_ignores` and the `exceptions` of `boundary_types` accept a seen site.
3. Model seam. `archkeel_model::rule_premises(model, rule)` lists the premises of one rule as
   `UsedPremise { kind: PremiseKind, subject }`, with `PremiseKind { DoorReach, ExternalUser,
   Declared(PremiseName) }`. `Model::declares_premise(name)` tells whether the contract declares a
   premise. `archkeel_model::premise_words` is the one place of the words. A new declared premise
   is a variant of `PremiseName` (contract crate, `premises.rs`) and a branch in `declared`
   (`model/src/premises.rs`); the code that cancels a gap under it asks `declares_premise` first.
4. Frame (additive). `premises` maps each PASS rule that rests on a premise to its premises
   (`kind`: the word of `PremiseKind`; `subject`). `assuming` holds the premises of the run in
   words: `the declared reach of N doors`, `N stated external users`, then the words of each
   declared premise, joined by `and`. `assumed` and `door_reach` do not change. The system frame
   joins `premises` of its parts and writes `assuming` for the whole system.
5. Text. The header word of a PASS run with a rule under a premise is
   `PASS assuming <assuming>`, not `PASS`. The reason says
   `all N rules pass; M pass assuming <assuming>`. The premise block lists the applied door
   declarations, then each other kind with its subjects, then the rules. The shell accepts any
   kind word; it needs no change for a new premise. The bare word PASS stays only for a run with
   no stated premise.
6. Page. The verdict badge reads `PASS assuming <assuming>`, the title
   `All N rules hold; M hold assuming <assuming>`, a note names the premises, and the rules
   section lists each rule under a premise with its subjects. The heading `<h1>Verdict: PASS</h1>`
   stays: it is the fixed anchor that the shell checks against the status of the frame.
7. The self-contract of the shell states one external user (`SHELL-PUBLIC-HAS-A-USER`), so the
   shell self-check now reads `PASS assuming 1 stated external user`.

Proof: [premises_tests.rs](../../../native/contract/src/premises_tests.rs) (the contract key),
[premises.rs](../../../native/model/src/premises.rs) (the kinds and the words),
[html_premise_tests.rs](../../../native/report/src/html_premise_tests.rs),
[html_blocks_tests.rs](../../../native/report/src/html_blocks_tests.rs) (the door reach page),
[test_cli_native_unused_public.py](../../../tests/test_cli_native_unused_public.py)
(`test_a_pass_that_rests_on_stated_external_users_is_never_a_bare_pass`, python3.12 runs the
plant), [test_cli_text_output.py](../../../tests/test_cli_text_output.py)
(`test_a_pass_under_a_premise_is_never_the_bare_word`),
[test_cli_python_door_reach.py](../../../tests/test_cli_python_door_reach.py).
