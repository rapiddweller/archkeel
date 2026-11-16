# AD-672 A self-check pin may only shrink, and growth needs a reason

**Status.** Accepted. Owner decision of 2026-11-16 (prevention bundle, measure M1). Part of #880.

**Reason.** `tools/native_expected.py` made the self-check equal to its pin, but `--write` regenerated the pin, so a new gap, UNKNOWN rule or violation entered without a person. A gate that the next merge can repin prevents nothing.

**Decision.**
1. Growth is a new gap, a new violation, a new UNKNOWN reason, or a rule that is new and not PASS or has a worse status (PASS, UNKNOWN, FAIL) than before.
2. Growth enters only through the growth file next to each pin: `native/expected-growth.json` and `docs/architecture/target/shell-expected-growth.json`. Each raised item has an `entry` (the item as the tool prints it) and a `reason` of at least 10 characters.
3. `--write` refuses growth that the growth file does not list. `--base-ref origin/main` (set by `make self-validate-native` and `-shell` when that ref exists) fails when the pin has growth against its version on main that the growth file does not list.
4. The lead may raise the ratchet; the reason is also logged in the decision log. A smaller pin is no growth and stays equal to the result (the gate still fails on a stale pin).

**Rejected.** A second pin file as a ceiling (two files that drift); a count limit (hides which item grew).

**Limit.** The file can be edited by hand; the check reads the diff against main, so a hand edit of the pin without an entry fails the PR gate, and an entry without a reason fails the test.

**Tests.** `tests/test_native_expected_gaps.py`: `test_growth_names_...`, `test_growth_needs_an_entry_with_a_reason`, `test_write_refuses_a_new_unknown_and_takes_a_listed_one`, `test_every_growth_entry_of_the_repository_has_a_reason`.
