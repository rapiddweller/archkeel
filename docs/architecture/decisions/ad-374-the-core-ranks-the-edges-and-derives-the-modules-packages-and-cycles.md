# AD-374 The core ranks the edges and derives the modules, packages and cycles

**Status.** Accepted. Epic #880, WP6 slice S3 (design WP6-0, section C; AD-363, AD-370, AD-372).

**Decision.**
1. `archkeel-model` computes the strongly connected components and the condensation ranks with
   an explicit stack (`condensation.rs`). The input depth never touches the call stack: a chain
   and one cycle of 100 000 modules are tests.
2. A rank is the longest path in the graph of the components. The reference engine sorts its
   queue, but each topological order gives the same longest path, so no tie break changes a
   rank. The members of a component are sorted, and each section is sorted by id. A seeded test
   compares 500 graphs with a copy of the reference algorithm.
3. Each node set is the node set of the reference engine. An edge row ranks over the ends of
   the edges of its level (`aggregate_edges`), so an edge to a package outside the reply has a
   target rank. A module or package row ranks over its table; an edge to a node outside the
   table changes no rank.
4. A macro body is a typed row of its own (`MacroBody`), not an import. It adds one fan-in and
   one fan-out only for a pair of two different modules of the reply that no edge has
   (`count_macro_bodies`). It never changes a rank or a cycle (AD-349).
5. The part of the model that only the reply and the settings give is the `Graph`: modules,
   packages, imports, macro bodies, edges, measures and cycles. The core derives it one time per
   run, moves it into the `Model` when the contract is usable, and keeps it until an input
   changes (#1059 item 1).
6. The core writes the full rows of `dependency_edges`, `modules`, `packages` and `cycles` from
   the `Graph`. These sections need no contract, so a case with a contract that the core cannot
   use is compared too. The frame field `edges` (rows without ranks) is removed: the harness
   compares the `dependency_edges` rows of the frame field by field with the Python engine on
   the same reply, because the oracle keeps only key fields of a large section.
7. Slice S3 decides no rule kind. The design gives `no_component_cycles` to S7 and
   `layer_order` to S5 (lead decision L-17). Transitive paths are not part of S3 (L-13).

**Reason.** Each direction and cycle slice reads the ranks and the cycles. A wrong rank or a
missed cycle breaks them all. Rows are facts, not verdicts, so they change no PASS.

**Python replaced.** `ir/graph.py:11` `strongly_connected_components`, `ir/graph.py:90`
`condensation_ranks`, the ranks of `check/evaluation/topology.py:25` `aggregate_edges`,
`topology.py:79` `package_records`, `topology.py:115` `module_records`, `topology.py:182`
`_cycle_records`, `topology.py:220` `_backed_package_cycles`, `topology.py:247`
`cycle_sections`, `check/evaluation/imports.py:35` `count_macro_bodies` and
`check/evaluation/evaluate.py:1157-1161` (the macro count and the unmeasured symbol count).
They go when the store path is the only path.

**Differences to Python.** None. The four sections are equal on each of the 189 cases whose
reply the store accepts: 2 211 edge rows with ranks, 1 422 module rows, 618 package rows and
25 cycle rows. The other 378 cases name `missing input: no valid collector reply`.

**Rejected.**
- Recursion as in the reference engine. A deep import chain overflows the stack.
- One condensation per level for all rows. The node sets differ (point 3); the rows must be
  equal also when an import names a package outside the reply.
- The rows inside `Model`. A run whose contract the core cannot use yet has no model, and the
  harness then compares no edge.

**Limit.** The store accepts two profiles, so the parity holds on 189 of 567 cases. A module
name that repeats in a reply keeps the fan counts of that name; the store refuses it today.
The 8 cases `s3/*` add a tie of ready nodes, a cycle across packages, a roll-up package
cycle, disconnected cycles, a self import, an edge outside the reply and macro bodies.

**Tests.** `native/model/src/condensation_tests.rs`, `topology_tests.rs`, `cycles_tests.rs`,
`edges_tests.rs`; `native/core/src/engine_tests.rs`
(`a_run_derives_its_model_one_time_until_an_input_changes`), `dual_run_tests.rs`;
`tests/test_native_core.py`
(`test_the_s3_sections_equal_python_on_every_case_whose_reply_the_store_accepts`);
`tests/test_dual_run_shell.py`.
