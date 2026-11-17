# AD-708 A use of a name through a Python module object is the import of that name

**Status.** Accepted (owner order: fix the false PASS). Part of #880, closes #1415. It closes the first open false PASS of AD-504.

**Reason.** `interface_boundary` judges import records. `import app.lib` then `app.lib._priv.secret()` has one record, the public module `app.lib`, so the rule gave PASS. Python 3.12 runs the consumer, and `app.lib._priv.secret.__module__ == "app.lib._priv"`: the call reaches the private submodule through the public module object. The same held for `import app.lib as lib`, `from app import lib`, and a private name `app.lib._x`. `from app.lib import _priv` was already FAIL.

**Decision.**
1. `survey/module_uses.rs` reads each whole-module binding of a module of the scan: `import a.b` binds `a`, while `import a.b as c` and `from a import b` bind `a.b`. Each attribute load through such a binding is a use of that name. A chain goes on through each child module of the scan, and stops at the first name that is no module.
2. `imports.rs` writes each use as an import record of its own. The record is resolved as `from module import name` (the submodule, or an attribute of the package, with the AD-450 ambiguity), and it has no binding. The core then judges it as any import: a private submodule or a name with `_` is FAIL, and a public name needs its publication route.
3. A module object escapes on any other use of the binding: a bare load, a chain that ends at a module, a namespace attribute (`__dict__`, `__all__`, `__setattr__`, `__delattr__`), a store or a delete. Then the import of that binding gets `symbols_known = false`, so the rule is UNKNOWN (`UnreadBinding`). `import a.a` and `from a import a` give the same record, so such a binding counts as escaped.
4. The store accepts `symbols_known = false` for a whole-module Python import statement. This is the documented meaning of the field.

**Why it is sound.** A name that Python reads through a module object is read either by a load that item 1 records, or after an escape, which item 3 makes UNKNOWN. A local name with the spelling of a binding counts as the binding: it can add a record or withhold a proof, never remove one.

**Measured.** Native, shell and system self-checks are as pinned on main (no growth, AD-672).

**Tests.** `tests/python_interface_module_plants.py`: the plant of #1415, an alias, a package binding and a private name are FAIL, a public name is PASS, and an escaped module object is UNKNOWN. On main `ec20eeb31`, the four FAIL forms gave PASS. `tests/python_review_plants.py` drops `d-S4-attr-through-module` from `OPEN`. `survey/module_uses_tests.rs`.
