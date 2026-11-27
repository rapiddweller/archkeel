# AD-1175 An annotation value is clean only when every binding of it is closed

**Status.** Accepted. Issues #2156 and #2157. It replaces point 4 of [AD-1173](ad-1173-a-module-that-evaluates-annotations-holds-each-value-it-cannot-name.md) (the set of tainted names) and its limit "an imported name".

**Reason.** The tainted-name set listed ways to bind a name, so Codex found a new way in each of nine rounds: an unrelated attribute with the same name, `T.__bound__` of a `TypeVar`, an alias, an import alias, a held text. The set also ignored the module a name comes from: `cfg.py: s = "__import__('app.lib')"` and `from cfg import s; x: s` loaded `app.lib` through `get_type_hints`.

**Decision.** In a module that evaluates annotations (AD-1173), each annotation-valued expression is *clean* or a `dynamic_import` site. One walk (`hazards_annotation_scopes.rs`) lists every binding of every name by scope: assignment, unpack, `:=`, `+=`, loop and `with` targets, `except` and `match` captures, parameters, `def`, `class`, imports. Attribute stores are keyed by receiver and name. `clean` reads only that table (`hazards_annotation_clean.rs`, `_resolve.rs`):
1. A string is clean when its text parses and its text is clean (depth 8). Text over the parser bound is a site.
2. A name is clean when every binding of it (after removing equal texts; at most 8) is clean: a builtin, a class or function, an assignment of a clean value, an import that is clean under rule 3. A cycle or an unreadable binding is not clean.
3. An imported name is clean when its module is in the standard library (the union of `sys.stdlib_module_names` of Python 3.11 to 3.14, a table in code) or is `typing_extensions`, and the scan writes no attribute of that module; or when the module is in the scan and the name is clean there. `import m` and `m.Name` follow the same rule for `Name`. A third-party name is a site: no record in the scan proves it a class.
4. An attribute `R.a` is clean when `R` is a module (rule 3) or a class of the scan and every binding of `R.a` (class body, any store of the name, `setattr`) is clean, else its base classes decide. Any other receiver (an instance, a call result, a parameter, a `TypeVar`) is a site.
5. A call of a standard type factory is clean when each argument after the name is clean (`bound=`, constraints, `default=`).
6. A write by a name that the table cannot read makes no name of the module closed: a computed `setattr`/`delattr`, a write into `globals()`, `vars()`, `locals()` or `x.__dict__`, `__setattr__`. A read of those is no write.
7. The scan writes an attribute of a standard module when a store or `setattr` has a receiver that its imports name as that module. A computed name writes any attribute of it.
Unchanged from AD-1173: any reach of `__annotations__`; `TypedDict`, `NamedTuple`, `make_dataclass` and `ForwardRef(name)` calls; the annotation of a local variable is no annotation.

**Effect.** Verdicts do not move on CE (`23bd48d9`), EE (`560d5c7ef`) or FastAPI 0.163.0. CE: 0 new sites. EE: 1 (`construction/factory.py`: `SetupContext` comes from a module with a computed `setattr`). FastAPI: 11 to 66 gaps, all in `fastapi.dependencies.utils`, which was already UNKNOWN: third-party names (pydantic, starlette) and `_compat/v2.py` and `params.py`, which hold a computed `setattr` or `object.__setattr__`.

**Cost.** A store `x.name = v` whose receiver no import names (`self.date = 1`) may write the attribute `name` of any module, so names `name` of standard and scanned modules are sites in the whole scan. The first parameter of a method is no proven receiver: `Patch.patch(module)` passes a module. A decorator that is not from the standard library may replace a class or function: the name is unknown.

**Limit.** A third-party class is a site until a record proves it (YAGNI: no contract list now). A computed `setattr` makes its whole module opaque (the safe choice). A module that only a library evaluates is not gated.

**Tests.** `tests/test_collector_false_pass_python_annotation_closed.py` (cross-module, standard-module write, receiver and `TypeVar` plants; controls) with the 31 plants of `..._class.py`. With the rule disabled 48 plants fail; with the standard-write check disabled the assignment plants fail.
