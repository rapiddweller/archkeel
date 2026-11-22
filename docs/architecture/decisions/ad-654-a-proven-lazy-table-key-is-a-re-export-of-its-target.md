# AD-654 A proven lazy table key is a re-export of its target

**Superseded in part by [AD-1058](ad-1058-receiver-annotation-and-exposure-proofs-of-the-trojan-horse-rules-are-tightened.md).** A lazy `__getattr__` that reads its keys with a computed `getattr` keeps a trojan horse site, so its proven keys are dropped until a contract declares the site.

**Status.** Accepted. Part of #880. It amends AD-560, AD-504 and AD-450.

**Reason.** AD-560 proves that a lazy `__getattr__` imports only modules that its table names. It does not prove what the function returns. So `from P import X` stayed an import of an unknown name of a module with `__getattr__`. A use of such a name escapes `P` and each module below it (AD-504). For `pydantic` v2.14.3 the root escaped. This gave 98 `reexport_ambiguity` gaps, no publication route through the root, and no symbol facts below it: 0 of 8,304 calls resolved. A bounded import call does not bound the returned value. A `python3.12` plant imports the module of the entry and then returns another module.

**Decision.**
1. *Return proof* (`lazy_return.rs`). The body of the AD-560 function runs once for each key of the table, with the parameter set to that key. It also runs once for a name that is no key. The values are strings, the entry of a key, `getattr(import_module(target), literal)`, `import_module(target)`, `globals()` and unknown. `import_module` must be the callee that AD-560 proves. `getattr` and `globals` must be builtins that the module does not bind.
   - A test that the strings decide picks its branch: `==`, `!=`, `is None`, `in` the table, `and`, `or`, `not`. Any other test runs both branches. A name that the branches bind to different values is unknown after them.
   - A loop over `table.items()`, `.keys()` or `.values()` runs once for each entry, in dict order. A key keeps its first place and takes its last value.
   - A key is proven when each `return` that its run reaches gives the same value: an attribute of a target module (`Attr`), or a target module (`Module`). A run that ends without `return` gives `None` and proves nothing.
2. *Stores.* Each `globals()[k] = v` of any run must have a string `k` that is a key of the table. If it does not, no key is proven. A `k` that names the table, a global that the function reads or a module dunder also proves no key. The `v` must be the proven value of `k`, else `k` is not proven. The probe of `_handle_fromlist` calls `__getattr__` once before it binds the name, so even the first import sees a stored value.
3. *Forms that prove nothing.* A statement that the run does not read (`try`, `while`, `with`, `del`, `match`, a nested scope, `global`), `break` or `continue` in a loop, a walrus, a store into anything but `globals()`, and a `globals()` value that is used outside a subscript store.
4. *Binders* (`lazy_agree.rs`). `__getattr__` runs only for a name that the namespace lacks. A key that the module binds keeps its proof only when every binder gives the same value. A binder can be an import, also under `TYPE_CHECKING`, which may run or not. It can also be a star import of a module whose literal `__all__` lists the key. `from . import name` of the package reads the key itself. A star import of a module without a literal `__all__` proves no key. A key that names a submodule or a package directory is proven only when its value is that submodule, because the import of the submodule binds that name.
5. *Who loses the proof.* A module with a hazard site outside the AD-560 cover keeps no key. A module that escapes keeps no key, because another module can then write a key. The escape walk and the import walk repeat until no module loses its keys.
6. *Use.* `from P import k` with a proven key reads its source, as `from T import x` or `import T` does:
   - the escape walk (`uses.rs`) uses that binding;
   - the import walk does not call `from P import k` ambiguous when `k` is a proven submodule key;
   - the route of `P.k` has the hop `T.x` (`routes.rs`);
   - the symbol facts and the call count read a view of the import records with the source (`lazy_cover::viewed`).
   The import records, their targets and the edges do not change.

**Why it is sound.** The run follows each path that Python can take for a key. A path that the strings do not decide is followed both ways, and its values meet as unknown. A stored value is the value that a later import gives. Item 2 makes it equal to the proven value. A binder of the key in the module gives the same value by item 4. A write from another module escapes the module (AD-504), and item 5 then removes the proof. A write through `sys.modules` or `exec` is a gap with the effect `every_module` (AD-564). An exception binds nothing. On `AttributeError` the fallback of `_handle_fromlist` imports the submodule of the key name, and item 4 makes that the proven value.

**Kept gaps.** A name that is no key keeps the old reading: an import of an unknown name of a module with `__getattr__`. This covers the second return path of `pydantic` (`_getattr_migration`). A `__getattr__` that is not a table (`return app` for `name == "app"`, DATAMIMIC CE) is not read. A module-level `__getattr__ = getattr_migration(__name__)` beside a plain binding stays unread too. Python calls it for that name while the module is partly initialized, so the binding alone does not decide the value.

**Measured.** Release core, `validate --json`, base fb1bb9bb4 and this change:

| project | `reexport_ambiguity` | calls resolved | rules |
|---|---|---|---|
| pydantic v2.14.3 | 98 -> 7 | 0 -> 175 of 8,304 | 1 PASS, 4 UNKNOWN before and after |
| DATAMIMIC CE | 4 -> 4 | 1,438 -> 1,438 of 13,190 | 176 PASS, 100 UNKNOWN before and after |
| DATAMIMIC EE | 6 -> 6 | 4,051 -> 4,051 of 37,163 | 256 PASS, 223 UNKNOWN before and after |

The return proof holds for all 153 `pydantic` keys. The binder check drops 2 (`MISSING`, `ValidationError`): an assignment under `TYPE_CHECKING` binds them. Of the 7 gaps that stay, 6 come from the escape of `pydantic.v1`. The last one is `from . import types`, and `types` is no key. No rule status changes. The rules of `pydantic` stay held by the real doors of K4 (AD-564). The resolved calls stay low because many target modules have their own `__getattr__ = getattr_migration(__name__)`: a use of a name from them still escapes that module.

**Tests.** `survey/lazy_return_tests.rs`: twelve plants, each checked against what `python3.12` binds for `from app import name` at two imports. They cover a key, a name that is no key, a key bound under `TYPE_CHECKING` to another value and to the same value, a table written later, a second return path, a return of another module, a store of another value, a run without `return`, a store under an unknown name, a submodule key and the route hop.
