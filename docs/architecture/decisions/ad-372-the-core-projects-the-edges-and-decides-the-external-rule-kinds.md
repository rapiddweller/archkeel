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
4. Protocol change of AD-360 point 7: the request is `archkeel-dual-run-2`. It adds `namespace`
   (from `archkeel.toml`), `profile` and `standard_library` (the names that the profile table of
   the shell gives for that profile). The core reads no configuration and names no language. It
   binds the settings to the reply by a check and refuses by name (exit 3): a profile that is not
   the profile of the reply, a module or package outside the namespace (`evaluate_source`), and a
   standard library with more than 1 024 names, an empty, NUL or over 128-byte name, or a duplicate.
   The final request of M1 must guarantee the same: namespace and standard library are bound to
   the reply by a check, never trusted. Edge rows need only the reply and these settings.
5. The rows of `dependency_edges` hold the ranks of the condensation (S3), so the section moves to
   S3. The frame carried the edge rows without the ranks in `edges` until
   [AD-374](ad-374-the-core-ranks-the-edges-and-derives-the-modules-packages-and-cycles.md) wrote the ranked rows. The rows of `imports`
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
- A rule that Python passes is a named gap of S4: 19 `external_dependency_scope` and 21
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
store accepts; Python marks them for two profiles, and a test fails when the store accepts a
third. The core cannot check that the standard library belongs to the profile: the shell table
gives it. The dual-run shell reads it from `ir/profiles.py`; the host owns it when `ir/` goes.
Edge parity is shown on 181 of 559 cases only (2 070 rows): the store accepts two profiles of protocol 8 and 9.
Behind the inside-tree class are 3 + 2 Python FAIL rules, behind the refused-reply class 5.
`make dual-run` with the S2 families compares 6 FAIL and 5 UNKNOWN `external_dependency_scope`
and 3 FAIL and 7 UNKNOWN `complete_external_scope` rules as equal; the 16 cases `s2/*` give
the FAIL and UNKNOWN cases of AD-360 point 10.

**Tests.** `native/model/src/edges_tests.rs`, `native/eval/src/external_tests.rs`,
`native/core/src/dual_run_tests.rs`; `tests/test_native_core.py`
(`test_the_s2_kinds_and_the_edges_equal_python_or_name_their_slice`);
`native/model/src/settings_tests.rs`; `tests/test_dual_run_shell.py`.
