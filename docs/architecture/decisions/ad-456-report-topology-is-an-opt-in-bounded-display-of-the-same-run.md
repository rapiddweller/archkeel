# AD-456 Report topology is an opt-in, bounded display of the same run

**Status.** Proposed. Part of #880. It extends AD-422 and AD-432.

**Decision.**
1. `archkeel report --topology` sets `topology: true` in the scan request. Without it the core builds
   nothing, and the frame and the time of a `validate` or `report` run stay as before.
2. Only the Rust core builds the `topology` section, in `native/core/src/topology_projection.rs`.
   It reads the model, the collector reply and the ruling that the same run made. It decides nothing.
   It never changes a verdict, a gap or an exit code. `Ruling::frame` stays the only maker of frame bytes.
3. The section has `version` (1), `complete`, `gaps`, `truncated`, `budgets`, `total`, `components`,
   `modules`, `edges` and `component_edges`.
   - A module has an ownership: `owned`, `unowned` or `ambiguous`.
   - An edge has a resolution: `resolved`, `unresolved` or `external`. The same pair in two
     resolutions gives two edges, with two identities.
   - An edge ID is a stable ID over the level, source, target and resolution.
   - An edge lists the rules whose FAIL rows cite one of its imports. The links come from the
     evaluated violations (`archkeel_report::rule_with_edge_links`). No second evaluation runs.
4. Budgets: 4,096 components, 10,000 modules, 20,000 edges, 20,000 component edges and 5 evidence
   locations for each edge. A total over a budget sets `truncated`, clears `complete` and keeps the
   exact total. The lists keep the first rows in sorted order. A short list never hides its size.
5. `complete` is true only when the scope of the ruling is `complete` and nothing is truncated.
   A scope gap of the run is copied into `gaps`.
6. `src/archkeel/cli/core_topology.py` decodes the section with typed values. It refuses an unknown
   field, version, budget, ownership or resolution, a count that differs from its list, a repeated
   identity, an incoherent `complete` or `truncated`, and a rule link that is not a row of the frame.
   It makes no decision. A requested section that is absent is a refusal.
7. The public API of `archkeel-report` adds one function: `rule_with_edge_links`.

**Reason.** Readers need the structure behind a verdict: who owns a module, which edges exist and
which edges a rule row cites. Computing it in the shell would create a second reader of the model.

**Rejected.** A section in each frame: it costs every run. A topology built in Python: a second
decision path. A silent cut at a budget: a short list looks complete. A new crate: not needed.

**Limits.** The display covers the root graph and the imports that the collector reports.
Edges between a pair of modules in several files merge into one row. Rule links exist for FAIL rows
that cite an import; an UNKNOWN row has no link. HTML output is not part of this record.

**Tests.** `tests/test_cli_report_topology.py` (small Rust and TypeScript projects, mounts,
unresolved edges, the three budgets, byte stability, plain frame equal without the section, forged
and absent sections). `native/core/src/topology_projection_tests.rs` (edge identities).
