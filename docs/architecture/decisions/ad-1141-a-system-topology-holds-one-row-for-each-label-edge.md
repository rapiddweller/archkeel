# AD-1141 A system topology holds one row for each label edge

**Status.** Accepted. Issue #2067. It extends [AD-618](ad-618-the-report-draws-one-page-for-a-system.md).

**Reason.** A real checkout (`jlowin/fastmcp` at `fbdb50f8a`) runs as a system of many parts. Each part writes the component edges `unowned -> external` and `unowned -> unresolved`. These edges name no component, so their id (level, source, target, resolution) is the same in each part. `system_topology.rs` appended the lists of all parts. The shell then refused the run with `core_error: topology: repeated identity`, and Studio had no first view. The message named no identity.

**Decision.**
1. The core merges the component edges of the parts by id: the counts and `evidence_total` add up, the evidence keeps the first 5 rows, and the rule links join. A scan of all parts in one run would give the same row.
2. The core sets the totals `component_edges` and `evidence_per_edge` from the merged rows. It sets `truncated` when one edge has more than 5 evidence rows.
3. A component, a module or a rule that two parts name still refuses the run (`unique`). Two different things never become one.
4. The shell refusal names the list and the repeated ids: `topology: repeated identity in component_edges: EDGE-…`.

**Rejected.**
- Drop the repeated rows in the shell. It hides a real conflict.
- Add the part to the id of a label edge. The Explorer draws one `external` node for each part, and the id would differ from the id of one scan.

**Limit.**
- Module edges are not merged. A module name is unique (rule 3), so their ids do not repeat.
- This change cannot enable a PASS. It changes the topology view, not a rule verdict.

**Tests.**
- `system_topology::tests::a_label_edge_of_two_parts_is_one_row_with_the_sum_of_both`
- `system_topology::tests::two_parts_that_name_one_module_stay_refused`
- `tests/test_cli_core_topology_identity.py`
