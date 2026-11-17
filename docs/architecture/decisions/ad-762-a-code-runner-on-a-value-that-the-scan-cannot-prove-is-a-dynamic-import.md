# AD-762 A code runner on a value that the scan cannot prove is a dynamic import

**Status.** Accepted (lead order: the Python false PASS bundle). Part of #880, closes #1520. It amends AD-539.

**Reason.** AD-539 cleared the dynamic-import gap of a local name `code` by its spelling, and named one open class: `code = provider.code; code.interact()` with an unknown `provider`. A provider from outside the scan can hand in an object whose `interact` imports `app.lib`. Python 3.12 confirms the import, and `NO-IMPORT` from `app.consumer` to `app.lib` gave PASS.

**Decision.**
1. A runner of the `code` module (`interact`, `InteractiveConsole`, `InteractiveInterpreter`) is a dynamic-import site when it follows one of these, whatever binds the name:
   - the name `code`;
   - a name that the file assigns from `code` or from an attribute `code` (`c = provider.code`);
   - an attribute `code` of any value (`provider.code.interact()`).
2. Any other use of a local `code` keeps AD-539: `code.value`, `str(code)` and `code.replace(..)` give no gap.

**Why it is sound.** The spelling of a name proves nothing about its value. A runner of the `code` module runs text that can import any module. Item 1 reads every form in which such a runner can follow a value named `code`. Over-approximation: an object with its own `interact` gives the gap.

**Measured.** The FastAPI reference project stays PASS 3/0/0 (it calls no runner).

**Tests.** `tests/test_collector_false_pass_python_code_runner.py` (the #1520 plant; Python 3.12 confirms the import). `survey/hazards_tests.rs` (local `code`, alias `c`, attribute `code`, `InteractiveConsole`). `survey/globals_read_tests.rs` (a runner on an unbound global `code`).
