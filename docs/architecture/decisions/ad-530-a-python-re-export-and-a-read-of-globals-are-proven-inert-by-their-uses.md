# AD-530 A Python re-export and a read of globals are proven inert by their uses

**Status.** Proposed. Part of #880. It amends AD-450, AD-472 and AD-504.

**Context.** On FastAPI 0.163.0 release 4.0.1 gives PASS for 3 rules. The core gave UNKNOWN: 13
`source_resolution_gap` held every rule and refused the `REQUIRES` scope proof. All 13 are
stricter than 4.0.1, and none is a real hazard.
- 8 `reexport_ambiguity` (`from fastapi import params`): `fastapi` and `fastapi._compat` were
  *written* (`uses.rs`, AD-504): a bare use of an imported name of unknown kind escapes its package.
- 3 `__globals__` (AD-450): `getattr(fn, "__globals__", {})` fed a lookup and a type evaluation.
- 1 `code`: a parameter named like the door module `code`. 1 `types`: `getattr(types, "UnionType")`.

**Decision.**
1. An imported name is *inert* when its origin cannot be a module of the scan, nor an alias of
   one (`uses.rs`, `value.rs`): a `def` or `class`; a literal or a display (AD-504); a value read
   only from the builtins `tuple`, `list`, `set`, `frozenset`, `dict`, `sorted` and the scalar
   builtins (each unbound in its module), from `.keys()`, `.values()`, `.items()`, and from names
   that are inert (kind `Derived`); or an import that leaves the scan. Each re-export is followed
   to its sole plain binder, in a module with no `__getattr__`, no write of an attribute, no
   hazard of a namespace and no submodule of that name. A call of any other function, an
   attribute, a subscript, a name with two binders and a module of the scan stay unknown. An
   inert name escapes nothing; the rest is as in AD-504.
2. A read of `__globals__` (`globals_read.rs`) is no gap when the dict only feeds `d.get("k")`,
   `d["k"]` and `"k" in d` with a literal key that is no door string, or a call outside the scan
   (an import that leaves the scan, or a pure builtin), or a function of the scan whose
   parameter does the same (bound 4, a cycle is not inert). The dict may be held by one local
   name that the function writes once. A return, a store, `.items()`, `**d`, an iteration, a
   computed key, `eval`, an unknown callee and a second write stay a gap.
3. A name that a function binds, and no import binds, is no door (`hazards.rs`). A comprehension
   variable binds in the comprehension only. `getattr(module, "name")` with a literal name that is
   no door string reads the one attribute `module.name`; it is a gap only if that name is a door.
4. Both candidate edges are not written for a really ambiguous name. A possible edge that does
   not exist gives a false FAIL for `forbidden_dependency` and `complete_requires`; the model has
   no grade for it. A shadowed, open or written package keeps its gap.
5. `setattr`/`delattr` writes no module of the scan when its first argument is a plain name that
   the innermost function, with its nested scopes, binds once, in its own scope, by `copy(arg)` or
   `deepcopy(arg)` (one positional argument) of the one plain module-scope import of `copy`
   (`copy_local.rs`), and no module of the scan is `copy`, `copyreg` or names a hook word
   (`__copy__`, `__deepcopy__`, `__reduce__`, `__reduce_ex__`, `__new__`, `copyreg`, the dispatch
   tables of `copy`, `f_locals`, `settrace`, `setprofile`). A parameter, an attribute or subscript
   of a local, a second binding, a global, a call result and a method `setattr` keep the gap.
   Truth (CPython 3.12): a copy of a module raises `TypeError`; only a hook, a `__new__`, a
   `copyreg` reductor or the memo of `deepcopy(x, memo)` gives a module; a copy keeps attributes;
   a frame write can rebind a local. A hook built at run time gives a module of the scan only by a
   use of it as a value: an escape (decision 1). The doors gain `inspect.getmodule`, the three `gc`
   object walkers and `f_globals`; a read of `f_globals` follows decision 2.

**Proof.** A bare use matters only if the value can be a module of the scan. Constants, scalars
and callables are not modules, and a container holds a module only through a name that is not
inert, or a call. A module that a container names is already a bare use of that module in its own
module. Release 4.0.1 counts no edge for any of the 13 forms: its edge for `from p import x` is
the submodule unless `__init__` binds `x`, and it reads `__globals__` as nothing.

**Where the core differs from 4.0.1.** Stricter: a package that another module writes, a name
that `__init__` rebinds, deletes or binds conditionally, and a dict that is iterated or passed to
an unknown callee keep their gap, where 4.0.1 gives PASS.

**Limits.** The survey reads no library code: a library function that returns the globals dict,
read by a computed key of the project, is not seen.

**Premise.** The Python collector states one assumption with each verdict (`Facts.scope_premise`,
AD-540): "code outside the scan roots hands in no module object of the scan". Decisions 1 and 5
rest on it. A PASS of a Python scan without it is refused by the frame reader.

**Results.** With decision 5 (2026-11-16): FastAPI 0.163.0 0 gaps, PASS 3/0/0 as 4.0.1 (main: 2
gaps of `copy_field_info`); pydantic v2.14.3 163. DATAMIMIC CE is not measured again.

**Tests.** `tests/test_cli_native_python_reexport.py` (plants of `python_reexport_plants.py`
and `python_setattr_plants.py`), `uses_*tests.rs`, `globals_read_tests.rs`.
