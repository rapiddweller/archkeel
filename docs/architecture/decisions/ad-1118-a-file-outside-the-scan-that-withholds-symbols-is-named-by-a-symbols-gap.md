# AD-1118 A file outside the scan that withholds symbols is named by a `symbols` gap

**Status.** Accepted. Part of #1963. It extends [AD-564](ad-564-a-gap-states-its-effect-and-holds-only-the-rules-that-read-it.md) (gap effects) and [AD-770](ad-770-code-of-the-repository-outside-the-scan-that-writes-a-module-of-the-scan-withholds-its-routes.md) (outside code).

**Reason.** A Python file outside the scan roots can give a module object of the scan. The survey then withholds the symbol records of each module that the file names or uses. On CE one script (`script/check_installed_authoring.py`) removed the symbol evidence of 540 modules: 0 of 16,391 calls resolved. The report did not name the file.

**Decision.**
1. The survey writes one gap for each site, or for each file with a use of a module: `outside_file_withholds_symbols: <file>[:<line>] <site> names N modules of the scan`. The facts keep the file and the line.
2. The gap has the new effect `Symbols { modules }`: the symbol records of these modules are withheld. Files, import edges and layout stay known.
3. A gap with this effect holds a rule only when the rule reads the code of a module (`ReadSet.code` in `gap_effects.rs`). These are `interface_boundary`, `boundary_types`, `protocol_declarations`, `unused_public`, `symbol_placement`, `call_owner`, `forbidden_call_argument`, `complete_requires`, `forbidden_construct`, a `forbidden_dependency` with `target_symbol`, and a rule kind that no slice decides. `forbidden_dependency`, `external_dependency_scope`, `complete_external_scope`, `sibling_isolation`, `no_component_cycles`, `complete_assignment`, `root_layout`, `layer_order` and `allowed_dependency` keep their verdict.
4. The effect only holds rules. It enables no PASS. The withholding itself does not change.
5. The facts protocol 11 is not released (4.0.1 has no schema 11), so its schema gets the new variant in place, as #1843 and #1968 did.
6. Attribution: one outside file gives all modules. With more files the survey runs the escape once more for each file, until each module has a file. No escaped module means no extra run.

**Rejected.**
- `Edges`, `Modules` or `EveryModule`: each holds rules that do not read symbols, so a PASS of an edge rule would turn UNKNOWN.
- A gap with no effect: it holds the whole scope.
- Text only, with no gap: it needs a new field in the survey reply, and the gap is the one typed way to name a cause.

**Limit.** A use of a module that the file reaches only through another file is not attributed to a file. The modules stay withheld and the gap of the other file names them. A file with many modules gives one gap for each hazard site.

**Tests.** `tests/test_cli_python_outside_withheld.py`: each edge rule stays PASS and the symbol rule goes UNKNOWN. Mutation: `Symbols` mapped to a whole-scope hold fails the test.
