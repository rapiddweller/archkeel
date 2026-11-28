# AD-1510 Only the real `sys.modules` is the import table of the typing guard

**Status.** Accepted. Issue #2240 (cause 2 of 5). It narrows [AD-568](ad-568-narrow-the-typing-factory-proof-to-the-statements-that-can-replace-a-factory.md).

**Reason.** The guard of AD-568 withholds the typing and class proofs for the whole scan when a statement can replace a standard library name. It took each name `modules` and each attribute `.modules` for `sys.modules`. In CE a local `modules: dict[str, str] = {}` in `expression_globals.py` (two writes, one delete) withheld the proofs of the whole repository: 13 hits in one file, and every call of a class stayed unproven.

**Decision.** The import table is (`survey/uses_typing_guard.rs`):
1. `X.modules` where `X` is a name that the module binds by `import sys` or `import sys as X`.
2. A name that the module binds by `from sys import modules [as N]`.
3. `.modules` of a receiver that is no plain name (a call, a subscript): it cannot be told from `sys`.

A local dict, a parameter or an attribute named `modules` is none of these. The guard keeps its write forms (a subscript store or delete with a computed key or a typing key, `update`, `setdefault`, `pop`, `popitem`, `clear`). It adds two rules so that the narrower match opens no path:
- A **bare use** of the table is a hit: `m = sys.modules`, `f(sys.modules)`, `sys.modules = d`. A read form is no bare use: `sys.modules[k]` as a load, `k in sys.modules`, a loop over it, `.get`, `.keys`, `.items`, `.values`, `.copy`, and a mapping reader such as `len`.
- A bare use of the name `sys` is a hit (`t = sys`, `getattr(sys, "modules")`). `sys.attr` is no bare use.

**Counter-examples that run** (`tests/test_cli_python_modules_table_guard.py`, each plant also runs under CPython and writes the real table): an alias, `from sys import modules`, the same with an alias, `import sys as s`, a function whose parameter is named `modules` and gets `sys.modules`, `sys.modules = {...}`, `getattr(sys, "modules")`, a copy `there = sys`, and `importlib.import_module("sys").modules`. Each one withholds the proof (UNKNOWN). A local dict and an attribute named `modules` keep it (PASS).

**Limit.** A write that goes through a name that is neither `sys` nor an alias that this module binds (a `sys` that another module hands in as a parameter) is not seen: the `sys` that a call returns is seen (rule 3), a parameter is not. This was already true for each other name than `modules`. A read of `sys.modules` makes its module hazardous (AD-450), as before.
