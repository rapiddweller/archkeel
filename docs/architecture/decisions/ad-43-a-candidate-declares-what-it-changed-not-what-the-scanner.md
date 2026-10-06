# AD-43 A candidate declares what it changed, not what the scanner counted or what every module already carries

Coverage counters no longer produce semantic changes. `_delta_records` returns
no records for `coverage`; `DeltaCoverage` already checks aggregate baseline/head
status, and observations retain full coverage for reports. Remove the redundant
projection plumbing.

`check/python_profile.py::crossing_imports`, shared by delta and ratchets, excludes
only the exact `(__future__, annotations)` boilerplate import. The analyzer retains
this source fact for other readers. `private_crossings` is unaffected.

Adding `ir/labels.py` with one import and one function had produced seven changes:
one dependency edge, five mechanical coverage counters and one future import.
These cuts reduce that to the useful edge. Another coverage-status semantic entry
would duplicate `DeltaCoverage`; collector filtering would remove a fact needed by
reports and other readers ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).

The analyzer version stays unchanged. Delta schema rises to 1.3.0 because the same
observations now yield fewer changes; readers fail closed on changed meanings
([AD-8](ad-08-statement-constructs-are-class-a-rules.md)). Expectation schema stays
1.2.0: fields and dimensions are unchanged, and matching `checker_digest` already
binds evaluation to the running package. Other boilerplate imports need exact entries.

Checks: `tests/test_delta.py::test_one_module_with_one_intra_component_import_is_one_semantic_change`
expects one added edge; parity golden digests changed with schema bytes;
`docs/roadmap.md` records 7 -> 1.
