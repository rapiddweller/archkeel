# AD-1340 A reserved name that an exact `str` tests is data

**Status.** Accepted. Issue #2196. It narrows the string site of [AD-1059](ad-1059-a-standard-library-name-that-imports-by-a-string-is-a-trojan-horse.md) and [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md).

**Reason.** `type(name) is str and name in {"__globals__", "__builtins__", "__import__"}` lists names; it looks nothing up. The survey gave a `dynamic_import` site to each reserved string literal, wherever it stood, and each site held the rules UNKNOWN. A script-safety checker of the consumer has 11 such sites.

**First design, rejected.** The issue asked for a rule by form: a literal in `in`, `not in`, `==` or `!=` is data. Codex found nine bypasses in three rounds, each one a CPython 3.12 plant that imports `app.lib` with no gap: a comparison calls `__eq__` of the other operand with the literal, and that operand can be an instance of a class of the scan, a class that inherits one hook and defines the other, a class with a metaclass `__eq__`, a name that a walrus rebinds, a name that an unpacking assignment gives a hook, an element of the display that runs the hook while the set is built, or the next operator of a comparison chain. A rule by the form of the text cannot be closed; the type of the other operand is the proof.

**Decision.** One rule (`survey/inert_texts.rs`). A reserved string literal is no site when it stands in a comparison that:
1. is the operand right after `type(name) is str` in an `and` chain (nothing stands between, so the name cannot be written in between), has one operator, and has the name on its left; and
2. is `name in D`, `name not in D`, `name == "text"` or `name != "text"`, where `D` is a string literal, a set, tuple or list display of string literals only (or `frozenset`, `set`, `tuple` of one such display, with the builtin visible), or a name that the module binds once to such a display and uses only in comparisons of this form, and no other module of the scan imports it, reads it as an attribute, writes it as a string, or star-imports.

An exact `str` has the hooks of `str`, and a display of string literals builds without user code, so no code of the scan sees the literal. `type(name) == str` is no proof (a metaclass can define `__eq__`), `isinstance` is none (a subclass), and a test with no proof keeps the site. Every other place keeps the site too: a call argument, a store, a return, a dict key, a `match` case, a literal bound to a name, the left side of `in`, an iteration, a subscript or a method call of a bound display.

**Narrowing.** Yes: a text that was a site is now none, so a rule can reach PASS where it was UNKNOWN. The proof is the type of the left operand and the content of the right operand.

**Limit.** The rule clears only the guarded form. It clears nothing on the CE and EE copies: their forms are `token == "__import__"`, `node.value == "__builtins__"` and bound sets of an operand of unknown type, and both define `__eq__` with `__hash__` in a class. A check of the type by a statement (`if type(n) is not str: return`) or by `isinstance` is not read. A type flow of the other operand would clear more; it is not built.

**Tests.** `inert_texts_tests.rs` (4 tests: 11 guarded forms that stay data, each beside a class with `__eq__` and `__hash__`; 26 forms that keep the site; 12 bound forms; 4 other-module forms). `tests/test_collector_false_pass_python_reserved_text.py`: 6 controls stay PASS (CPython leaves `app.lib` unloaded) and 19 plants stay UNKNOWN or FAIL (CPython imports `app.lib`), among them the bypasses of the first design.
