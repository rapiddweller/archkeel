# AD-514 The Python collector writes the symbol declarations that it binds once

**Status.** Proposed. Part of #880. It extends AD-512 to Python. PR 2 of 5 (L-173).

**Reason.** A Python reply had no `symbols` section, so the symbol part of a UML target was one
named gap. Release 4.0.1 decides it from each definition that `ast` shows. Python binds a name when
the module runs: a second binder, a decorator that replaces the object or a base that changes the
kind makes the text a wrong witness.

**Decision.**
1. The reply of the Python survey declares the section `symbols` (store: `imports`, `symbols`,
   `unknowns`). It has one record for each class, function, method and class attribute that
   rule 2 to 7 admit. `Profile::symbol_facts` is true for Python.
2. **One reader of binders.** `survey/bound.rs` (AD-504) is the one function of "the names that a
   statement binds" for a module body and a class body (each target form, pattern, walrus, `for`,
   `with`, `except`, import, `del`, star import, `global`); `survey/writes.rs` is the one reader of
   "the objects that a statement writes to". This change adds no second one.
3. **Sole binder.** A record is written for a direct statement of a module or class body that is
   the only statement that binds its name and is a `def`, a `class`, `name = value` or
   `name: T`. Any other binder of the name (second `def`, `if`, `try`, `for`, `with`, `del`,
   `global`, walrus, `match`, star import, `type X = ...`) writes no record. The name is then
   absent: UNKNOWN "absent symbol", never a verdict. A class that is not written writes no member.
4. **Module gate.** A module writes no record when the survey names a hazard site in it
   (`exec`, `globals()`, `locals()`, `sys.modules` ...), when `opaque_surface` holds it (another
   module writes to it, AD-504) or when a star import binds its names.
5. **Decorators.** A decorated class writes no record. A decorated function writes one only for
   exactly one of `staticmethod` or `classmethod`, read as the builtin (no binder of the name in
   the module), and only in a class body; the record has `method_kind`. Any other decorator
   (`property`, `functools.wraps`, `overload`, a call) may replace the object: no record.
6. **Class kind.** A class has a record only when its kind is proven: no keyword (`metaclass=`,
   `total=`), and each base is `object`, `typing.Protocol`, one class of `enum` (`Enum`,
   `IntEnum`, `StrEnum`, `Flag`, `IntFlag`), a builtin `Exception`, or a class of the same module
   that has a record. A base is read through its one `from typing import` or `from enum import`
   statement. `Protocol` gives an interface only when it is a direct base; an enum base passes
   the enum kind on. Else no record. Enum literals are the plain names of a body with only
   constant values; any other body form lists none.
7. **Members.** A method is a `def` of rule 3 and 5. An attribute is a name of rule 3 in a class
   body (`name: T` has the annotation, `name = value` is `static`, as 4.0.1). The class has the
   two member inventories, always `partial`: a base, a metaclass, a decorator or a write after the
   class body (`C.x = v`, `setattr(C, ...)`, `cls.x = v`) can add a member. A module with an
   attribute write whose base is not `self` writes no member. Instances (`self.x` in `__init__`,
   `setattr(self, ...)`, `__dict__`) are no class member. A module-level value and a function
   inside a function write no record (AD-377: a value needs its admission).
8. **Sites are not stated.** The Python reply declares no `calls` and no `references`, and a class
   has no `base_declarations`. `Profile::symbol_sites` is false for Python. The model gives
   each relationship (`inherits`, `realizes`, `mixes_in`, `calls`, `references`, `creates`,
   `instance_of`) the cause "the python collector states no symbol sites" and builds no base
   receipt: a FAIL for a missing base is impossible. PR 3 writes the sites.

**Fixture rows.** H-uml stays UNKNOWN (exit 2): its target lists seven site relationships. Of its
21 entities 18 move from "states no symbol facts" to PASS; `item`, `Text` and `VERSION` stay
UNKNOWN (rule 7). `fixtures/matrix.json` does not change.

**Plants (75, `tests/test_cli_python_symbols.py`).** Against 4.0.1: 43 equal, 27 PASS to UNKNOWN, 5
FAIL to UNKNOWN (3 release FAILs are false: `globals-write`, `dict-instance`, `nested-function`; 2
true FAILs are lost: `unknown-base`, `enum-rebound`). Of the 27, 20 are a release PASS where Python
does not bind what the target plans; 7 are a true PASS that the core withholds (dataclass,
`NamedTuple`, `TypedDict`, `Generic`, a module value, a number default, a subscript). The core
never gives PASS where the truth differs, and never FAIL where it agrees.

**Text.** Only a name, a dotted name, `None`, `True` and `False` (`unparse` stays behind the dump:
ungated, its recursion between files is a self-check FAIL). A number, subscript or string: no record.

**Rejected.** A record for each binder, as TypeScript has it (a statement that no record shows
would pass); a `complete` inventory (no proof of writes after the class body); a gap record for
each omitted name (each such run would be partial for every other rule).

**Open** (`docs/known-limits.md`). A local `self` that holds a class; a C extension or `globals()`
of another module that writes a class; a member that a base `__init_subclass__` adds.
