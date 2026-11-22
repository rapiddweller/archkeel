# AD-1057 A cycle step names the declared edges that it uses

**Status.** Accepted (owner decision, 2026-11-22). It extends [AD-1052](ad-1052-a-contract-declares-a-trojan-horse-site-by-its-name.md), which lists the declaration ids behind a FAIL.

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.

**Reason.** A cycle FAIL that rests on a declared possible import named all declarations of the rule, up to 20 ids. A reader could not tell which declaration closes the cycle, or which module edge it adds.

**Decision.** Each applied declaration keeps its declared imports as pairs of the scanned target and the id of the import (`Applied.edges`). A declared import has a stable id that the cycle step already holds. The frame part `explain.cycles[].path[]` adds `declared` to a step that uses such an import. Each entry has `declaration`, `source` (the module of the site) and `target` (the module that it may load). The text report prints one line below the cycle row for each edge: `<source> -> <target>, declared by <ids>`; at most three edges, then a count.

**Limits.** The list is empty for a step that has an observed import. It shows the edges that the scan knows by module; a declaration that loads an external prefix adds no cycle step.

**Tests.** `tests/test_cli_python_trojan_horse_cycle.py` (a declared load closes a cycle; Python really imports the target).
