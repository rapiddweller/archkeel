# AD-52 A violation is named by what it is, and a baseline may hold the ones already there


`ir.baseline` derives a `ViolationFingerprint` from a violation record: the rule ids it cites
and its `subjects`, which the analyzer already sorts and which hold module names, a construct
owner or the members of a cycle, by kind. No position enters it, so an unrelated line inserted
above a violating import leaves it unchanged, while the `VIO-` id beside it still moves. The
fingerprint does not replace that id. Violations sharing a fingerprint — two `getattr` calls in
one function — are counted rather than told apart. `validate --baseline <file>` reads a file of
those fingerprints with their counts, and reports only where the file and the code disagree: a
count the file understates is a new violation, one it overstates is a violation somebody fixed.
Both are `failures` with exit 1, and a run whose baseline is exactly right exits 0 with
`declared_rules: FAIL`, because the violations are still there and still reported. Only
`rule.violated` is answered this way; every other diagnostic still exits 2, as does a baseline
that cannot be read (`baseline.invalid`). `--write-baseline` writes the observed violations to
that path, and writes nothing from a run that exited 2. `validate` without `--baseline` is
unchanged, and so is every other command. Reason: a contract that states the target
architecture is contradicted by the code that has yet to reach it, so `validate` is red by
design and gates nothing; the workaround was to declare the debt edges as `requires` or
`allowed_dependency`, which makes the contract describe the code instead of the target and
lets a *new* import over such an edge pass unseen. A baseline keeps the target intact and
moves the debt into a file that shrinks. datamimic CE had built this outside Archkeel by
decoding `architecture.json` with `ir.codec.decode_canonical_model`, an internal module.
Rejected: replacing `VIO-` with the fingerprint, because the fact id is what ties a violation
to its evidence, and two violations may legitimately share a fingerprint. Hashing the
fingerprint into one opaque token, as `stable_id` does elsewhere, because this file is read
and widened in review diffs (#11), where `CONSTRUCT-NO-DYNAMIC | shop.model.probe.read` is the
whole point. Keying on the violation's `title`, because prose is not an identity. Failing only
on new violations while reporting resolved ones as information, because a budget allowed to
exceed the code lets a violation someone removed return unreported — the flaw of the
workaround this replaces; requiring exact counts makes the file state today's debt and makes
shrinking it part of the change that shrinks it. Storing the fingerprint as one delimited
string, because a component label may contain the delimiter. Keeping `ANALYZER_VERSION` at
0.22.0 is deliberate: the derivation reads records the analyzer already writes, and no record
changes. Limit: a fingerprint follows a rename of what it names — move the violating code to
another module, or rename the function around a `getattr`, and the entry reads as one
violation resolved and one new, which is honest but noisier than a diff would be. Two
violations of one rule that name the same subjects are one entry, so the file cannot say
*which* two. The file is compared, never authenticated: `check`'s digest chain does not cover
it, and nothing yet stops a change from widening it — that is #11. Check:
`tests/test_baseline.py::test_a_moved_violation_keeps_its_fingerprint`,
`tests/test_baseline.py::test_two_violations_in_one_function_share_a_fingerprint_and_are_counted`,
`tests/test_baseline.py::test_a_baselined_violation_passes_while_validate_alone_still_fails`,
`tests/test_baseline.py::test_a_new_violation_of_the_same_rule_in_another_module_fails`,
`tests/test_baseline.py::test_a_resolved_baseline_entry_is_reported`,
`tests/test_baseline.py::test_a_smaller_count_for_a_known_fingerprint_is_resolved_too`,
`tests/test_baseline.py::test_a_baseline_does_not_hide_any_other_diagnostic`,
`tests/test_baseline.py::test_a_missing_baseline_file_is_exit_two_with_a_diagnostic`,
`tests/test_cli.py::test_validate_baseline_writes_then_gates_on_new_violations` and
`tests/test_schema_drift.py::test_baseline_schema_accepts_what_the_writer_writes_and_the_parser_reads`.

