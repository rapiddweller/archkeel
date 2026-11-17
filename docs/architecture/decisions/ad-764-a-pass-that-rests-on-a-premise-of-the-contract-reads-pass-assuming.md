# AD-764: A PASS that rests on a premise of the contract reads "PASS assuming"

Status: accepted (lead order, 2026-11-17). Fixes #1549. Part of #880. Generalizes AD-664.

1. Problem. AD-664 made a PASS under a declared door reach read "PASS assuming the declared reach
   of N doors". An `unused_public` rule skips each item that its `external_users` list names
   (AD-670, AD-746). Such a rule then read as a plain PASS, although the entry is a claim of the
   contract about code outside the scan, not a proof.
2. A premise is a statement of the contract about what the scan cannot see, on which a PASS
   rests. Two kinds exist: the declared reach of a door site (AD-664) and a stated external user
   of a public item. A stated external user is a premise of a rule only when no other component is
   proven to use the item (`archkeel_model::stated_users`). An entry for an item with a proven user
   is no premise. Policy entries on facts that the scan sees are no premises: `allowed_sources`,
   `allowed_type_ignores` and the `exceptions` of `boundary_types` accept a seen site.
3. Frame (additive). `premises` maps each PASS rule that rests on a premise to its premises
   (`kind`: `door_reach` or `external_user`; `subject`: the door site or `module:name`).
   `assuming` holds the premises of the run in words: `the declared reach of N doors`,
   `N stated external users`, or both joined by `and` (`archkeel_report::premise_words`, the one
   place of these words). `assumed` and `door_reach` do not change. The system frame joins
   `premises` of its parts and writes `assuming` for the whole system.
4. Text. The header word of a PASS run with a rule under a premise is
   `PASS assuming <assuming>`, not `PASS`. The reason says
   `all N rules pass; M pass assuming <assuming>`. The premise block lists the applied door
   declarations, the stated external users and the rules. The bare word PASS stays only for a run
   with no stated premise.
5. Page. The verdict badge reads `PASS assuming <assuming>`, the title
   `All N rules hold; M hold assuming <assuming>`, a note names the premises, and the rules
   section lists each rule under a premise with its subjects. The heading `<h1>Verdict: PASS</h1>`
   stays: it is the fixed anchor that the shell checks against the status of the frame.

Proof: [html_premise_tests.rs](../../../native/report/src/html_premise_tests.rs),
[html_blocks_tests.rs](../../../native/report/src/html_blocks_tests.rs) (the door reach page),
[test_cli_native_unused_public.py](../../../tests/test_cli_native_unused_public.py)
(`test_a_pass_that_rests_on_stated_external_users_is_never_a_bare_pass`, python3.12 runs the
plant), [test_cli_text_output.py](../../../tests/test_cli_text_output.py)
(`test_a_pass_under_a_premise_is_never_the_bare_word`),
[test_cli_python_door_reach.py](../../../tests/test_cli_python_door_reach.py).
