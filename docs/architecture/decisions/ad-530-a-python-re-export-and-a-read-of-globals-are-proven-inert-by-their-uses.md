# AD-530 A Python re-export and a read of globals are proven inert by their uses

**Status.** Proposed. Part of #880. It amends AD-450, AD-472 and AD-504.

**Context.** On FastAPI 0.163.0 release 4.0.1 gives PASS for 3 rules. The core gave UNKNOWN: 13
`source_resolution_gap` held every rule and refused the `REQUIRES` scope proof. All 13 are
stricter than 4.0.1, and none is a real hazard.
- 8 `reexport_ambiguity` (`from fastapi import params`): `__init__` binds none of the names, but
  `fastapi` and `fastapi._compat` were *written* (`uses.rs`, AD-504). A bare use of an imported
  name of unknown kind escapes its package. Examples: `from fastapi import __version__` passed as a
  value, and `Undefined = PydanticUndefined`.
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

**Proof.** A bare use matters only if the value can be a module of the scan. Constants, scalars
and callables are not modules, and a container holds a module only through a name that is not
inert, or a call. A module that a container names is already a bare use of that module in its own
module. Release 4.0.1 counts no edge for any of the 13 forms: its edge for `from p import x` is
the submodule unless `__init__` binds `x`, and it reads `__globals__` as nothing.

**Where the core differs from 4.0.1.** The core stays stricter: a package that another module
writes, a name that `__init__` rebinds, deletes or binds conditionally, and a dict that is
iterated or passed to an unknown callee keep their gap, where 4.0.1 gives PASS.

**Limits.** A library function that returns the dict, and project code that then reads
`__builtins__` from it by a computed key, is not seen (the survey does not read library code). A
value with an external origin may carry a scan module only through code outside the scan.

**Results.** On main `6cc397932` against this change, gaps before to after: FastAPI 0.163.0 6
to 2 (the 4 `__globals__` and `types` gaps go; 2 `reexport_ambiguity` stay), pydantic v2.14.3
321 to 307 (14 `dynamic_import`), DATAMIMIC CE 59 to 59. No rule moves to PASS: each project keeps
a gap that holds its rules.

**Tests.** `tests/test_cli_native_python_reexport.py` (33 plants: the row of the core before and
after, the row of 4.0.1, and a run under CPython), and the Rust tests `uses_tests.rs`,
`globals_read_tests.rs`.
