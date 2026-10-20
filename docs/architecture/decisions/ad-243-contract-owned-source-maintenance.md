# AD-243: Contract-owned source maintenance

Own source, tests and tools have a hard target ceiling of 500 physical lines per file.
Split by responsibility with explicit interfaces. Size alone does not justify
fragmenting one coherent responsibility. Eliminating duplicated decisions takes priority.

Native file selection, authenticated inventory and the unchanged hard 500-line rule
belong to the separate `feat/contract-source-maintenance` change. Its implementation,
exact provenance exclusions and unresolved findings are preserved there. PR #621
contains the Performance/DRY changes; it does not implement this additional rule.

SPOT owners identify canonical decisions. Consumers use the same decision and
profile; validation remains at each trust boundary. Structural similarity cannot
prove all semantic duplication absent.

- `archkeel.check.python_profile:is_crossing_import` owns the cross-package symbol
  predicate shared by raw metrics and decoded comparisons.
- `archkeel.ir.facts.stable_id` owns deterministic record identity; structural copies
  remain native review findings.
- `archkeel.ir.source_records.source_name_visibility` owns source-spelling privacy;
  language API visibility and explicit exports remain separate decisions.

Existing rules, coupling ceilings and UNKNOWN proof requirements remain unchanged.
The unresolved-call budget stays tightened from Main's 840 to 827.

[Contract](../../../architecture-contract.json) ·
[Crossing controls](../../../tests/test_python_crossing_policy.py) ·
[Profile controls](../../../tests/test_dependency_profile_selection.py) ·
[Identity controls](../../../tests/test_duplication.py)
