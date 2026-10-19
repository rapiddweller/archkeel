# AD-243: Contract-owned source maintenance

Own source, tests and tools have a hard ceiling of 500 physical lines per file.
Split by responsibility with explicit interfaces. This supplements AD-4; moving
arbitrary chunks into numbered files does not establish meaningful ownership.
Eliminating duplicated rules and decisions takes priority. Size alone does not
justify fragmenting one coherent responsibility; unresolved target findings stay visible.
Pinned upstream code, generated outputs and data are distinct from maintained source.
Their exclusion requires exact provenance; existing oversized source gets no exception.

The native Contract owns this ceiling and its repository-file selection. Input ports
collect snapshot-bound text sizes independently of language parsing. Core owns the
comparison and its receipts. Missing or incomplete evidence remains UNKNOWN; known
oversized files remain failures. Generic module receipts cannot certify text coverage.

SPOT owners identify canonical decisions. Consumers use the same decision and the
same effective profile; boundary validation remains at each trust boundary.
Structural similarity is a review signal and cannot prove all semantic duplication absent.

`archkeel.check.python_profile:is_crossing_import` owns the existing cross-package
symbol measurement predicate shared by raw metrics and decoded comparisons.
`archkeel.ir.facts.stable_id` owns deterministic record identity. Its Contract owner
must follow the implementation; copying it must remain a native review finding.
`archkeel.ir.source_records.source_name_visibility` owns source-spelling privacy; language
API visibility and explicit exports remain separate decisions.

No component permission, acceptance ceiling or UNKNOWN proof requirement is relaxed.

[Contract](../../../architecture-contract.json) ·
[Crossing controls](../../../tests/test_python_crossing_policy.py) ·
[Profile controls](../../../tests/test_dependency_profile_selection.py) ·
[Identity controls](../../../tests/test_duplication.py) ·
[File-rule controls](../../../tests/test_max_file_lines.py)
