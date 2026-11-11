# AD-361 Transitive package reach is one record per package

**Status.** Accepted. Epic #880, step 1 of the plan change after the plain stage timings.

**Decision.**
1. From ArchitectureIR 2.11.0, the section `transitive_paths` holds one FACT record per package that
   reaches other packages only through a third one: kind `transitive_package_reach`, id
   `REACH-<package level, source>`, subjects `[source]`, and data `level`, `source` and the sorted
   `targets`. It holds the same pairs as the records of 2.10 (one per pair, kind
   `transitive_package_dependency`, with the shortest path and its edge ids). A package with no
   such target has no record.
2. `ir/graph.transitive_targets` computes the targets from the package dependency edges. A reader
   that needs the path of one pair computes it on demand: `_bfs_parents` of the same ordered graph
   gives the shortest path that 2.10 recorded.
3. The schema files `architecture-ir-decoded-2.11` and `architecture-ir-python-decoded-2.11` describe
   the record. `command-result-14.0` accepts observations of 2.11. The decoder still reads every
   earlier version, with the records of 2.10.

**Reason.** No rule, view or page reads the path records (checked by search and by the full test
suite; the report pages hold no path). They were the largest section of the host: 746 000 records on
a workspace of 289 Rust crates, with an id, a title and an edge id for each step. They grow with the
square of the package count.

**Measured** (289 Rust crates, median of 3, macOS). Verdict maps equal on that workspace, x35,
H-typescript and the native tree. Store path: host peak 6 655 to 5 702 MiB, store peak 1 970 to
1 727 MiB, run 216 to 102 s. Python path: host peak unchanged (6 619 MiB): the decode of the reply
holds the peak there, before the topology exists.

**Rejected.**
- A null section. It would say "not observed", and claims on the section would turn UNKNOWN.
- An empty section. It would claim that no package reaches another through a third.
- A table of pairs. It is as large as the records, without the ids.

**Limit.** The pages show no transitive path, so none is computed on demand yet. A consumer of 2.10
that reads `data.path` gets no path from 2.11.

**Checked by** `tests/test_graph_transitive_paths.py` (the targets equal the pairs of one search per
pair on 300 random graphs) and `tests/test_graph_topology_level_types.py`.
