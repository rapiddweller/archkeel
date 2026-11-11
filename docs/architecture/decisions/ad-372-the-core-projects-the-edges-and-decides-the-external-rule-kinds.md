# AD-372 The core projects the edges and decides the external rule kinds

**Status.** Accepted. Epic #880, WP6 slice S2 (design WP6-0, section C; AD-363, AD-370).

**Decision.**
1. `archkeel-model` splits the imports of the reply as `split_imports` does: an unresolved import
   and a macro body leave the imports. Each other import keeps its typed target (local, external
   package, builtin). An unresolved import whose site (module and evidence) no collector gap names
   is an `Incomplete` (`UnknownImports`), so each rule without a violation is UNKNOWN.
2. The model projects the imports to module and package edges as `aggregate_edges` does. A module
   edge needs a target module of the reply, a package edge a target package in the namespace;
   neither keeps a self edge. An edge holds one source and one target, so a later record of
   transitive paths (one record per package with its targets) is a type of its own.
3. `archkeel-eval` decides `external_dependency_scope` and `complete_external_scope`. An external
   import matches a dependency by its package name, any other import by the scope of its target.
   The order of the decision is the order of AD-370; a PASS still needs the scope proof of S4.
4. Protocol change of AD-360 point 7: the request is `archkeel-dual-run-2`. It adds `namespace`,
   which the shell reads from `archkeel.toml`, and `standard_library`, the top-level names that
   the profile table of the shell gives for the profile of the reply. The core reads no
   configuration and names no language (`Settings`). The core takes an edge row only from a
   reply and these settings, so a contract that the core cannot use still has its edges.
5. The rows of `dependency_edges` hold the ranks of the condensation (S3), so the section moves to
   S3. The frame carries the edge rows without the ranks in `edges`, and the harness compares
   them with the Python engine on every case whose reply the store accepts. The rows of `imports`
   are the records of the store plus the marks of the typed targets (`Porting::Store`).

**Reason.** The edges are the input of each direction and cycle slice; a wrong edge list breaks
them all. The two external kinds read only the import targets and the modules, so their FAIL and
UNKNOWN are sound before the scope proof. The standard library is a property of the profile; a
list in the core would name a language.

**Python replaced.** `check/evaluation/topology.py:25` `aggregate_edges`,
`check/evaluation/imports.py:13` `split_imports`, `ir/import_gaps.py:14`
`derived_unresolved_imports`, `check/evaluation/unknown_imports.py:11` `unknown_import_failure`
(as a coverage cause), the target marks of `check/evaluation/evaluate.py:1100-1110`, and
`check/evaluation/rules.py:273` `_external_dependency_violations` and `:317`
`_external_completeness_violations`. They go when the store path is the only path.

**Differences to Python (all equal or stricter).**
- A rule that Python passes is a named gap of S4: 19 `external_dependency_scope` and 20
  `complete_external_scope` rules of the corpus.
- A Python UNKNOWN for a cause that S2 does not see (a hidden Rust edge, the subject check of
  another rule) is the same named gap: 7 and 2 rules.
- An unresolved import that a droppable pair gap names is not counted, so `UnknownImports` is
  never larger than the failures of Python. `dependency_edges` is named until S3.

**Rejected.**
- The core reads `archkeel.toml`. The shell stays the only reader of the configuration.
- A standard library list per profile in the core. The model and the core name no language.
- Compare the edges only through the rules. A wrong edge that no S2 rule reads stays unseen.

**Limit.** The marks of an external package and a builtin target apply to every reply that the
store accepts (TypeScript and Rust). When the store accepts another profile, the shell must send
whether that profile marks them. The dual-run shell reads the standard library from
`ir/profiles.py`; the host shell owns that table when `ir/` goes. `make dual-run` with the S2
families compares 5 FAIL and 5 UNKNOWN `external_dependency_scope` and 3 FAIL and 7 UNKNOWN
`complete_external_scope` rules as equal, and 2 058 edge rows on 180 cases; the 15 cases `s2/*`
give the FAIL and UNKNOWN cases of AD-360 point 10.

**Tests.** `native/model/src/edges_tests.rs`, `native/eval/src/external_tests.rs`,
`native/core/src/dual_run_tests.rs`; `tests/test_native_core.py`
(`test_the_s2_kinds_and_the_edges_equal_python_or_name_their_slice`); `tests/test_dual_run.py`
(the edge comparison without ranks, the settings of the shell).
