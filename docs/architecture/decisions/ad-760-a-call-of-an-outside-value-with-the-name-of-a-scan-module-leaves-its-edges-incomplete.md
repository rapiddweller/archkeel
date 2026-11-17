# AD-760 A call of an outside value with the name of a scan module leaves its edges incomplete

**Status.** Accepted (lead order: the Python false PASS bundle). Part of #880, closes #1519. It amends AD-450.

**Reason.** A module outside the scan and the standard library can load the module whose name it is given: `from plugin_vendor import load` then `load('app.lib')`. The scan cannot read the loader, and no import statement names `app.lib`. Python 3.12 has `app.lib` in `sys.modules` after the call, yet `NO-IMPORT` from `app.consumer` to `app.lib` gave PASS.

**Decision.**
1. A binding is external when an import of a module outside the scan and the standard library makes it (in any scope of the file).
2. A call whose callee goes back to an external binding through attributes, calls and subscripts (`plugin.loader.load(..)`, `namespace()[key](..)`) is checked: each string argument that is a dotted path (or `module:attribute`) whose longest prefix is a module of the scan names that module.
3. Such a call is a gap `external_loader: <module>` with the effect `Edges` of the module of the call: its outgoing edges are not complete. A prefix that is the module of the call or a package above it gives no gap, because Python imports those already.
4. A callee from the standard library is a door when it is one (AD-450, AD-472), and a builtin or a function of the scan is read: they give no such gap.

**Why it is sound.** A loader outside the scan is reached only through a value that the file gets from an import of it. The gap holds each rule that reads an edge of the caller. Over-approximation: a callee that does not load, with a string that names a module, keeps the gap.

**Open, not accepted.** A loader that reaches the file as a parameter or an attribute of an unknown value (`def f(load): load('app.lib')`) gives no gap. This is the unknown-value class next to AD-539, and it is listed in `docs/known-limits.md`.

**Measured.** The FastAPI reference project stays PASS 3/0/0. Its calls with a string that names one of its modules are `logging.getLogger("fastapi")` (standard library), otel calls with `"fastapi"` or `"fastapi.*"` names whose only module prefix is the package above the caller, and `scope.get("fastapi.telemetry")` on a parameter (item 1 does not apply).

**Tests.** `tests/test_collector_false_pass_python_loaders.py` (Python 3.12 confirms the import), `survey/external_loader_tests.rs`.
