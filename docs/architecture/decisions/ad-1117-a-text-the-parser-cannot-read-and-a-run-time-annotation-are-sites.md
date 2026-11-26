# AD-1117 A text the parser cannot read and a run-time annotation are sites

**Status.** Accepted. Issue #2039. It extends [AD-1095](ad-1095-a-string-annotation-is-read-as-code.md).

**Reason.** Three routes still reached an evaluated string annotation with no site. CPython 3.12 loaded `app.lib` in each case and the verdict was PASS.
1. A string with 150 nested `[...]` around `__import__('app.lib')`. The parser bound refuses it, so it had no tree. CPython evaluates it.
2. `K.__annotations__ = {...}` or `f.__annotations__['x'] = ...`, then `typing.get_type_hints`.
3. `s = "..."` and `class K: x: s`.

**Decision.**
1. `parse::expression` tells a syntax error (`Unread::Syntax`, no site, as AD-1095 point 4) from a text over the bound (`Unread::Bound`). A text over the bound is a `dynamic_import` site at the string.
2. A store to `__annotations__` (an assignment, a subscript store, an augmented assignment, a `del`, or a method call on it) is a `dynamic_import` site. The write puts a string where no annotation position holds it.
3. A name in an annotation that the module assigns a string literal reads that string as code (AD-1095). A name that the module assigns an f-string, a `+` or `%` expression, or a `.format` or `.join` call is a site.

**Limit.** A deep text that holds no hazard is a site too (precision loss: the bound cannot tell). A name that gets its string from a call, a parameter or another module is not seen. A read of `__annotations__` is no site.

**Tests.** `tests/test_collector_false_pass_python_annotation_routes.py` (each plant makes CPython 3.12 write a line to a counter file; each control leaves the counter at 0) and two unit tests in `hazards_importers_tests.rs`.
