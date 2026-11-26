# AD-1098 A module that holds a hazard name is a site when it flows as a value

**Status.** Accepted. Issues #2016 and #2024. It extends [AD-1094](ad-1094-a-project-module-that-re-exports-a-standard-library-module-hands-on-its-trojan-horse.md) and [AD-1059](ad-1059-a-standard-library-name-that-imports-by-a-string-is-a-trojan-horse.md).

**Reason.** CPython 3.12 imports `app.lib` in each plant below, and `forbidden_dependency` gave PASS with no gap. The survey read a module with a hazard name only as the base of an attribute chain, and the re-export table of AD-1094 was keyed on the attribute name that follows a project module.

- `def f(): return cProfile`, then `util.f().run(text)`.
- `util.c = cProfile`, then `util.c.run(text)`.
- `from app.util import cp as x`, then `x.run(text)`.
- `def same(m): return m`, `alias = same(dis)`, then `alias.__dict__['Bytecode']`.

**Decision.**
1. A bare name that an import binds to a module that holds a hazard name (a trojan horse, an importer or a state name of AD-1059) is a `dynamic_import` site when it is read as a value: a return, an argument, an assignment, a list item. The read of an attribute of the name keeps the chain rule.
2. A bare name that a from-import binds to a name that a module of the scan re-exports (`from app.util import cp`) is a site as a value.
3. A chain from such a name (`x.run`) is read from the origin of the name, so `app.util.cp` plus `run` meets the re-export table.

**Rejected.** A value-flow analysis of function returns. The site at the first read of the value needs no flow and cannot miss a route.

**Limit (precision).** AD-1059 left a module above an importer (`logging`) out of the value rule. `getattr(logging, level)` and `helper(logging)` are now sites. The cost is UNKNOWN where PASS would be right; a project that wants PASS declares the reach.

**Tests.** `tests/test_collector_false_pass_python_module_value.py`: 8 plants (CPython 3.12 imports `app.lib`; the verdict must be UNKNOWN or FAIL) and 4 controls that stay PASS. A mutation that removes the three rules fails the plants.
