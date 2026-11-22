# AD-1041 Four reads that run no import are no trojan horse in the Python survey

**Status.** Accepted. Part of #1963. It amends [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md) (the trojan horse and state sites), [AD-574](ad-574-inert-door-attributes-keep-the-module-import-gap.md) and [AD-894](ad-894-a-plain-statement-is-no-import-door-in-the-python-survey.md) ("Kept gaps").

**Reason.** The trojan horse list matches names by spelling. Datamimic-ee has 91 gaps, and each gap that states `every_module` holds every rule outside the layout row (AD-564). Some of these sites read a value and run no import. The survey kept them as trojan horses.

**Decision.** `cleared` in `survey/hazards_inert.rs` drops a site when its syntax closes every use of the value:

1. `types.CodeType` and `types.FunctionType` in an annotation (a name, a `|` union, a subscript, a tuple or a list of these), and as the class argument of the visible builtin `isinstance`. The name form needs the existing unique import (`code_types`). The attribute form needs a name that is the standard module `types`.
2. `"text" in sys.modules` and `"text" not in sys.modules`, with a string literal and a name that is the standard module `sys` (one binding).
3. `globals().keys()` as the only argument of a visible `set`, `sorted`, `list`, `tuple`, `frozenset` or `len`.
4. `s = x.__spec__` in a function (`x` is a plain name, `s` has one binding and is local). Each use of `s` is a test `is None`, a read of `s.name` or `s.parent`, or `s.submodule_search_locations` as a test or as the argument of a pure builtin or `pkgutil.walk_packages`/`iter_modules`.

Each other use of the same names keeps its gap. An import statement keeps its gap (AD-574).

**Premise added.** A class that an annotation stores is not called by library code that reads the annotations. The text keys of the globals of one module name no code of another module.

**Not built, with the reason.**
- Trojan horse strings (`"__self__"`, `"__builtins__"`) in `==`, `in`, a set or a dict key. Python calls `__eq__`, `__ne__` and `__contains__` of the other operand with the string. A class can collect the strings and import with them. Only a proof of an exact builtin operand type clears the site, and the survey has no type proof. The operands that a literal proof can reach do not occur in datamimic-ee or datamimic-ce, so the rule would be dead code. The plants stay as tests.
- The import statement of `types`, `importlib.metadata`, `pickle`, `dill` and `pkgutil` when each use is inert. Another module can import the binding and call it, and the walk does not see this. A proof needs the module export set of the `uses` layer (AD-504). A text search for the name fails on `.metadata` in datamimic-ee.
- `pickle.dump` and `dill.dumps` of any value. Pickling a function whose `__module__` was written imports that module by name (the plant in the tests runs it in Python 3.12).
- `pkgutil.walk_packages` with a literal prefix and `import_module(name)`. The names are below the prefix, but the effect needs a bounded form in the facts and the model (GapEffect has none), and the loaded module can be written by its caller. A declaration of AD-664 states it.

**Tests.** `survey/hazards_inert_tests.rs` (each form and each use that keeps the site). `tests/test_collector_false_pass_python_door_census.py`: Python 3.12 runs each plant (the form plus a real import through the neighbour use, a class that collects strings, a variable, a set that a loop passes on). The rule is UNKNOWN or FAIL. A control for each form loses its gap, and `sys.modules`, `globals` and the attribute form of `types` give PASS.
