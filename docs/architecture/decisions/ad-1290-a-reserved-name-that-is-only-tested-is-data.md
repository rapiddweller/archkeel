# AD-1290 A reserved name that is only tested is data

**Status.** Accepted. Issue #2196. It narrows the string site of [AD-1059](ad-1059-a-standard-library-name-that-imports-by-a-string-is-a-trojan-horse.md) and [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md).

**Reason.** `name in {"__globals__", "__builtins__", "__import__"}` lists names; it looks nothing up. The survey gave a `dynamic_import` site to each string literal that names a trojan horse, wherever it stood, and each site held the rules UNKNOWN. A script-safety checker of the consumer has 11 such sites.

**Decision.** One closed rule (`survey/inert_texts.rs`). A reserved string literal is no site when it is:
1. an element of a set, tuple or list display (or of `frozenset(...)`, `set(...)`, `tuple(...)` of one display, with the builtin visible) that is the right side of `in` or `not in`; or
2. the right side of `in` or `not in` itself; or
3. an operand of `==` or `!=`; or
4. an element of a display of strings that is bound to a name when all of these hold: the module binds the name once (`Binders::count`); at least one use of the name is the right side of an `in` test and every use is one; no other module of the scan imports the name, reads it as an attribute, writes it as a string (`__all__`, `getattr(m, "NAME")`) or star-imports.

Each other place keeps the site: an argument of any call (`getattr`, `hasattr`, `__import__`, a library call), a store, a return, a dict key or value, a `match` case, a literal bound to a name, the left side of `in`, an iteration, a subscript or a method call of a bound display.

**Narrowing.** Yes. A text that was a site is now none, so a rule can reach PASS where it was UNKNOWN. The literal is data in these places only. A lookup that uses the tested name has its own site: `getattr(o, n)` with a computed name, `operator.attrgetter`, `__dict__`.

**Limit.** The left side of `in` (`"__import__" in names`) is not data: the rule is the one that was asked for. A bound display that a module reaches through an escaped module object (`dir`, `vars`) is only caught when the lookup itself is a site. A name that a star import of a module with the same last name takes is caught by the star-import test of any module.

**Tests.** `inert_texts_tests.rs` (4 tests: 14 forms that stay data, 15 forms that keep the site, 12 bound forms, 4 other-module forms). `tests/test_collector_false_pass_python_reserved_text.py`: 6 controls stay PASS (CPython leaves `app.lib` unloaded) and 10 plants stay UNKNOWN or FAIL (CPython imports `app.lib`). The mutation that marks every string literal inert fails 3 of the 4 Rust tests.
