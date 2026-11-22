# AD-1040 A loader under a foreign literal name writes no module of the scan

**Status.** Accepted. Part of #1963. It amends [AD-770](ad-770-code-of-the-repository-outside-the-scan-that-writes-a-module-of-the-scan-withholds-its-routes.md) point 3.

**Reason.** AD-770 point 3 clears two forms of a hazard site in a file outside the scan. Each other
site makes every module of the scan that a string of the file names escape. One CI script of
datamimic-ee names the package `"datamimic_ee"` in a string and loads a fixed test file with
`importlib.util.spec_from_file_location("smoke_selection", ...)`. All 1991 modules escaped.
21 `reexport_ambiguity` gaps and 0 resolved calls followed. Skipping the script gives 6 gaps and
4,063 resolved calls (#1963).

**Decision.** In `survey/outside_sites.rs`, a file outside the scan has a foreign loader when
it has at least one use of `spec_from_file_location` and each such use is a call that gives only a name and a
location, with a name that is a string literal. The literal must name no module of the scan, no
package above one and no prefix of one. In such a file these sites are no hazard:

1. each `spec_from_file_location` call;
2. each call of `module_from_spec` or `exec_module`;
3. the import statements of `importlib`, `importlib.util` and its two loader names.

Each other site of the file keeps its rule. A value use of `spec_from_file_location` (an alias), a
second call with a scan name, a computed name, a `loader` or `submodule_search_locations`
argument, `sys.modules`, `import_module`, `find_spec` and any other trojan horse end the proof.

**Why it is sound.** `module_from_spec` makes a new module object. Under a foreign name it is no
module of the scan. A module object of the scan can reach `exec_module` only through a use that
AD-504 already treats as an escape (a bare use, a store) or through a site that stays a hazard
(`sys.modules`, `import_module`). The loaded file is read by the walk (a Python file), searched as
native text (`.pyc`, `.so`), or it is a test source or outside the repository: the stated premise.
A `loader` argument could run a file that the walk does not read, so it ends the proof.

**Limit.** Python can run a text file through `SourceFileLoader` and a variable that the file does
not spell. That case is open before and after this change (the premise covers code that the walk does not read).
The 6 `reexport_ambiguity` gaps in `domains/registry/components.py` stay. A module object of the
scan is a list element or a call argument there. The escape rule of AD-504 (a bare use escapes) fires in
`uses::Uses::visit_expr`. A proof needs the receiver type and a proof of the callee parameter.

**Tests.** `survey/outside_tests.rs` (clears and stays), `tests/test_collector_false_pass_python_door_census.py`
(Python 3.12 runs each plant: a spec with a scan name, a scan module as loader target, a store, the state of the
import system; the control with a foreign name is PASS).
