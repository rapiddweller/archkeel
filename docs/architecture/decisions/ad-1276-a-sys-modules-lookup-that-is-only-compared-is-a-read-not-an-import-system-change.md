# AD-1276 A `sys.modules` lookup that is only compared by identity is a read, not an import-system change

**Status.** Accepted. Part of #2197. It narrows [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md) and extends the inert reads of [AD-574](ad-574-inert-door-attributes-keep-the-module-import-gap.md).

**Reason.** A scanned module that holds `found = sys.modules.get("math")` and uses `value is found` gave the site `import_system_change: sys.modules`. That site applies to every module and holds all rules UNKNOWN. The code only reads the table, and its value reaches no code.

**Decision.** `sys.modules.get(<text written in the source>)` is no site when each use of its value is an operand of `is` or `is not` (also against `None`, also in a chain). `is` runs no method of the value.

The lookup is read in two forms: inline in such a use, or bound by one statement `found = sys.modules.get("text")` in the body of a function. In the second form the name has one binding in the module and no `global` or `nonlocal`, and each load of the name in the function is such a use. `sys` must be the standard module bound once (the same fact as for `"text" in sys.modules`).

Everything else keeps the site: a truth test, a return, an argument, a call or an attribute on the value, `==` (it can run `__eq__`), `in`, a store, a lookup at module level (another module can import the name), a key that is no text, a second argument, `setdefault`, `pop`, `update`, an item write or delete, and `from sys import modules`.

**Truth test.** The first version also allowed a truth test (`if sys.modules.get("x"):`). Review (Codex P1) showed that a truth test runs `__bool__` or `__len__` of an object that a dependency put into the table, and that code can import a module of the scan. The verdict does not prove the type of the value, so the truth test keeps the site.

**Evidence.** The Rust unit tests list the allowed and the held forms. The CLI test `tests/test_cli_python_sys_modules_lookup.py` runs the issue and its counter-probes on a whole project. A mutation that turns the rule off fails the allowed plants. On the CE and EE copies the verdicts and the gap counts do not change: neither copy has a lookup of this form.
