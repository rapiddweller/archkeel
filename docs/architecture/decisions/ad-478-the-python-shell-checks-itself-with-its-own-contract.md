# AD-478 The Python shell checks itself with its own contract

**Status.** Proposed. Part of #880. It extends AD-335, AD-432 and AD-450.

**Decision.**
1. The Python shell `src/archkeel` has a contract: `docs/architecture/target/shell-contract.json`
   (schema 2.3.0), with the scan configuration `docs/architecture/shell.toml` and the page
   `docs/architecture/shell.md` (parts, marked graph, wanted rules). The files follow the precedent
   of `studio-ui.toml` and `target/studio-ui-contract.json`. They are not in `src/archkeel`,
   because that directory ships in the wheel and is the scanned scope.
2. The contract has 10 components by responsibility and 22 rules, all of kinds that the core
   decides: `complete_assignment`, `complete_requires`, `no_component_cycles` (component and
   module level), `layer_order`, `complete_external_scope`, `external_dependency_scope` and
   `forbidden_dependency`. Design intent: the shell decides nothing; only the `frame` part
   reads a verdict (`SHELL-NO-*-TO-FRAME`); nothing imports up (`SHELL-REQUIRES-COMPLETE`, `SHELL-NO-UP-TO-ENTRY`);
   no third-party package, so no analysis library (`SHELL-EXTERNAL-COMPLETE`); each standard-library
   door has one home (`SHELL-ONLY-*`).
3. `make self-validate-shell` runs the contract through the default CLI and the release core.
   `tools/native_expected.py` compares the result with `docs/architecture/target/shell-expected.json`
   (rows, reason kinds, gaps, violations, exit code). `make self-validate` runs the native and the
   shell check. `ci-check`, CI and Full call `make self-validate`.
4. The check found two real imports upward and fixed them: `core_binary` and `native_scan` took
   `CoreError` from `core_frame`; they now take it from `core_json`. A local name `code` in
   `core_only` was a `dynamic_import` gap (the survey reads names, not bindings); it is `status_code` now.
5. Result today: 22 PASS, 0 FAIL, 0 UNKNOWN. Release 4.0.1 gives 22 PASS on the same contract, and
   the same FAIL set on a copy with planted imports. No rule PASSes on the core where 4.0.1 does not.
6. A mixed tree is not possible today. The core reads a mounted contract (`inside`) of `native/`,
   but one scan has one profile, one namespace and one collector reply. The Rust packages lie outside
   the Python namespace, so every row of the tree is UNKNOWN. A tree needs a profile, roots and a
   namespace for each mount, and one collector reply for each mount, joined in the model.
7. The shell starts the core as a process: this is no import edge, and no rule kind can name it.
   `SHELL-ONLY-LAUNCH-STARTS-A-PROCESS` keeps the start in one module.

**Reason.** The owner ordered that Archkeel checks its own Python shell and its Rust core.

**Rejected.** A contract in `src/archkeel` (ships in the wheel). A forbidden rule for a library that no
module imports (it selects no module, and that makes the scope of the run incomplete). Faking a
mixed tree with a mount that decides nothing.

**Limits.** Not expressible: a forbidden library that is not imported; an empty
`allowed_sources` (refused); a rule on a name or a field inside a function; the process edge to
the core. The tools in `tools/` and the tests have no contract.

**Tests.** `tests/test_cli_shell_self_check.py`: pinned rows, planted imports, the mixed tree,
provenance and kinds, modules and graph. `tests/test_make_gate.py`: the targets and the refusal of a
self-check without a result.
