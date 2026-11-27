# AD-1340 A reserved name that is only tested is data

**Status.** Accepted. Issue #2196. It narrows the string site of [AD-1059](ad-1059-a-standard-library-name-that-imports-by-a-string-is-a-trojan-horse.md) and [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md).

**Reason.** `name in {"__globals__", "__builtins__", "__import__"}` lists names; it looks nothing up. The survey gave a `dynamic_import` site to each string literal that names a trojan horse, wherever it stood, and each site held the rules UNKNOWN. A script-safety checker of the consumer has 11 such sites.

**Decision.** One closed rule (`survey/inert_texts.rs`). A reserved string literal is no site when it is:
1. an element of a set, tuple or list display (or of `frozenset(...)`, `set(...)`, `tuple(...)` of one display, with the builtin visible) that is the right side of `in` or `not in`; or
2. the right side of `in` or `not in` itself; or
3. an operand of `==` or `!=`; or
4. an element of a display of strings that is bound to a name when all of these hold: the module binds the name once (`Binders::count`); at least one use of the name is the right side of an `in` test and every use is one; no other module of the scan imports the name, reads it as an attribute, writes it as a string (`__all__`, `getattr(m, "NAME")`) or star-imports.

A comparison calls `__eq__` of the other operand with the literal, so the rule needs a proof that no code of the scan runs there (Codex finding on this PR; a CPython plant calls `string.Formatter().get_field('0.' + name, ...)` from `Lookup.__eq__`):
- `==`, `!=` and a list or tuple test are data only when no statement of the scan defines or writes `__eq__` or `__ne__`;
- a set test hashes the operand first and compares only on a hash collision, so it needs a user `__hash__`: it is data only when the scan does not define or write both `__eq__`/`__ne__` and `__hash__` (a subclass can inherit one and define the other, so they need not stand in one class);
- `type(name) is str and name in ...` proves an exact `str` on the left when the comparison is the operand right after the check (nothing stands between, so a walrus cannot rebind the name): such a comparison is data whatever the scan defines. `type(name) == str` is no proof: a metaclass can define `__eq__`; `isinstance` is none either.

Each other place keeps the site: an argument of any call (`getattr`, `hasattr`, `__import__`, a library call), a store, a return, a dict key or value, a `match` case, a literal bound to a name, the left side of `in`, an iteration, a subscript or a method call of a bound display.

**Narrowing.** Yes. A text that was a site is now none, so a rule can reach PASS where it was UNKNOWN. The literal is data in these places only. A lookup that uses the tested name has its own site: `getattr(o, n)` with a computed name, `operator.attrgetter`, `__dict__`.

**Limit.** On the CE and EE copies the rule clears nothing: each defines `__eq__` and `__hash__` in a class, and the forms are `x == "__builtins__"` and bound sets of an unknown operand. The left side of `in` (`"__import__" in names`) is not data: the rule is the one that was asked for. A bound display that a module reaches through an escaped module object (`dir`, `vars`) is only caught when the lookup itself is a site. A name that a star import of a module with the same last name takes is caught by the star-import test of any module.

**Tests.** `inert_texts_tests.rs` (7 tests: 14 forms that stay data, 15 forms that keep the site, 12 bound forms, 4 other-module forms, 6 forms of an equality hook, the hash pair, the exact `str` guard). `tests/test_collector_false_pass_python_reserved_text.py`: 7 controls stay PASS (CPython leaves `app.lib` unloaded) and 16 plants stay UNKNOWN or FAIL (CPython imports `app.lib`). The mutation that marks every string literal inert fails 3 of the 4 Rust tests.
