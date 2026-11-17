# AD-786 A cycle row names its closed path and its sorted members

**Status.** Accepted. Part of #880, fixes #1657. Amends AD-484 (one ordered path through a cycle) for the violation rows of the frame.

**Context.** A cycle of the model is a strongly connected set with sorted members (AD-484). The violation row of a cycle (`details`) wrote `source` as the sorted members joined by ` -> ` and `target` as the first member, and the text output printed that as `a -> b -> c -> a`. That text claims imports that need not exist. On pydantic-core it printed `argument_markers -> build_tools -> ...`, but `argument_markers` imports only `py_gc` and `tools`. The HTML report already showed the real closed path from `Cyclic.path`.

**Decision.**
1. The row of a cycle adds `members`, the sorted set, and `path`, the closed path of AD-484 in import order. Each step has `from`, `to`, `imports` (the number of imports that make the step) and `evidence` (the evidence id of the first of them, one import site). The last step ends at the first member.
2. `source` and `target` of a cycle row stay as they were. They are the identity of the violation that the baseline reads (AD-546). The sorted set is the right identity because it does not change when an import inside the cycle moves. The schema states that this text is no path.
3. The text output shows the path, `a -> c -> b -> a`, with the `file:line` of one import for each step, in step order. A cycle without a closed path (an empty `path`) is shown as `cycle among a, b, c`. Other violation rows are unchanged.

**Consequences.**
- JSON readers get the ordered path and the set as separate fields. A baseline that accepted a cycle still matches it.
- The text line of a cycle names as many sites as the path has steps, not the first three sorted sites.

**Rejected.** Writing the path into `source`: every accepted cycle in a baseline would become new, and the path is a poor identity because it changes with the shortest closed path.

**Undo.** Remove `members`, `path` and `PathStep` from `native/report/src/violation_detail.rs`, the reader in `core_evidence.py` and `_edge` in `core_text.py`, then write the frame schema again.

**Tests.** `violation_detail::tests::a_cycle_names_its_closed_path_in_import_order_and_its_sorted_members`; `tests/test_cli_cycle_path.py`, a plant with the pydantic-core shape where the sorted members are no path (both tests fail on the core before this change).
