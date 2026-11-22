# AD-1058 The receiver, annotation and exposure proofs of the trojan horse rules are tightened

**Status.** Accepted (owner decision, 2026-11-22). It corrects [AD-1050](ad-1050-four-reads-that-run-no-import-are-no-trojan-horse-in-the-python-survey.md), [AD-1052](ad-1052-a-contract-declares-a-trojan-horse-site-by-its-name.md) and [AD-1053](ad-1053-a-computed-attribute-name-on-an-unproved-receiver-is-a-trojan-horse.md) after two independent reviews of #1968.

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.

**Reason.** Each review plant imports `app.lib` in Python 3.12 while the core said PASS. When a proof cannot be made sound, the clearing is removed and the gap stays. A precision loss is fine; a false PASS is not.

**Decision.**
1. Receivers. A class that the module binds once is the only proven receiver. `self` and `cls` are not (`C.get(f, name)`), a module is not (each module has `__builtins__`), a loaded local is not. A name or a loaded name counts only when the module binds it exactly once, so no parameter, pattern, `except` target, loop target or nested name rebinds it. A nested function or a lambda has no proof of its own.
2. Forms. `C.__getattribute__(x, name)`, `C.__setattr__(x, name, v)` and `object.__setattr__` have the receiver `x`. `delattr`, `__delattr__`, `attrgetter`, `methodcaller`, `getmembers`, `getmembers_static`, `get_referents` and `get_referrers` are read too. Each reference to one of these names, or to `vars` or `getattr`, that is not the callee of a direct call is a site (`g = getattr`, `map(getattr, ...)`, `partial(getattr, f)`, `ga = f.__getattribute__`). `x.__dict__` and `vars(x)` are a site, except directly subscripted with a literal key.
3. Annotations. `types.CodeType` and `types.FunctionType` clear only in the annotation of a local variable inside a function (Python neither evaluates nor stores it) and as the class argument of `isinstance`. Annotations of parameters, results, classes and the module are stored in `__annotations__`: they keep their site.
4. Exposure of a declared import. An importer that reads any attribute by a computed name (`getattr`, `setattr`, `delattr` with a name that is no literal, `vars`, `__dict__`, `__getattribute__`, `attrgetter`, `getmembers`) is exposed to every bound name. The premise stays: a name that an importer builds through any other text is not seen.
5. A declaration by `name` needs `scope` or `line` (contract 3.20.0). A site that has no line (`reexport_ambiguity`) has the scope `""`.
6. `loads` and `covers` are trusted by design: the scan does not check them. The text report says so. Each rule names its own declarations (`<rule>: under D-1, D-2`); the number in the header is for the whole run.
7. A lazy `__getattr__` table that the lazy proof of AD-654 accepts keeps its `getattr` calls without a site: the proof reads the keys of the table.

**Open limits.** The collector does not read these forms; each is a strict expected failure with an issue number in `tests/test_collector_false_pass_python_open.py`: see `docs/known-limits.md`.

**Tests.** `tests/test_collector_false_pass_python_trojan_attribute.py` (CPython runs each plant of the reviews), `tests/test_cli_python_trojan_horse_name.py` (exposure), `hazards_receiver_tests.rs`, `hazards_inert_tests.rs`.
