# AD-518 The Python collector writes the symbol declarations that it binds once

**Status.** Proposed. Part of #880. It extends AD-512 to Python. PR 2 of 5 (L-173).

**Reason.** A Python reply had no `symbols` section, so the symbol part of a UML target was one
named gap. Release 4.0.1 decides it from each definition that `ast` shows. Python binds a name when
the module runs: a second binder, a decorator that replaces the object, a base that changes the
kind or a write from elsewhere makes the text a wrong witness.

**Decision.**
1. The survey reply declares `symbols` (store: `imports`, `symbols`, `unknowns`), one record for
   each class, function, method and class attribute that rules 2 to 8 admit.
   `Profile::symbol_facts` is true for Python.
2. **One reader of binders.** `survey/bound.rs` (AD-504) is the one function of "the names that a
   scope binds" for a module body and a class body, with the headers of a nested class or def
   (bases, keywords, decorators, defaults, annotations) as binders of the enclosing body.
   `survey/declared/escapes.rs` is the one visitor of writes to a class and of escapes (rule 7).
3. **Sole binder.** A record is written for a direct statement of a module or class body that is
   the only statement that binds its name and is a `def`, a `class`, `name = literal` or
   `name: T = literal`. Any other binder writes none; the name is absent (UNKNOWN), never a
   verdict. A bare `name: T` binds nothing at run time, a value of another kind may be a function
   or a class, and `__x` is `_A__x`: no attribute. A class that is not written writes no member.
4. **Module gate.** No record when the survey names a hazard site (`exec`, `globals()`,
   `sys.modules` ...), when `opaque_surface` holds the module (AD-504) or a star import binds it.
5. **Decorators.** A decorated class has no record. A function has one only undecorated or with
   exactly one `staticmethod` or `classmethod` read as the builtin, and only in a class body.
   `__new__` is static and `__init_subclass__`, `__class_getitem__` are class methods by name.
   A drawn operation with no modifier against a static or class method is UNKNOWN (the drawn
   modifiers are compared only when stated; absent means plain, never "any").
6. **Class kind.** A record needs a proven kind: no keyword, no type parameter, and each base is
   one of the twelve builtins `object`, `Exception`, `BaseException`, `ValueError`, `TypeError`,
   `RuntimeError`, `KeyError`, `dict`, `list`, `tuple`, `str`, `int` (no binder in the module),
   `typing.Protocol`, one class of `enum` (`Enum`, `IntEnum`, `StrEnum`, `Flag`, `IntFlag`) by its
   one plain import, or a class of the module with a record. Literals of an enum: constants
   of distinct value (`R = 1; S = 1.0` is an alias) in a body of only those, methods and `pass`.
7. **Writes and escapes.** A base that may be a class opens the module (no class keeps a member):
   an attribute store, `del` or `+=` whose base is not the first parameter of an undecorated
   `def` of a class with builtin or module bases that is never rebound and is no
   `__init_subclass__`, `__class_getitem__` or `__new__`; `setattr`, `delattr`, `vars`; any use
   of `__setattr__` or `__delattr__`. A class name used other than as a call, a base, an attribute
   load or an annotation escapes: the class keeps no member, and no nested class.
8. **Inventories** are always `partial`. Instances (`self.x`, `__dict__`), a module value and a
   function inside a function write no record. Text: a name, a dotted name, `None`, `True`,
   `False`; a builtin name that the module binds is no text (`int = str`).
9. **Sites are not stated** (`Profile::symbol_sites` is false): each relationship is UNKNOWN
   "the python collector states no symbol sites", and no class has a base receipt. PR 3 writes them.

**Fixture rows.** H-uml stays UNKNOWN (exit 2): 20 entities, 8 relationships, 7 of them sites.
16 entities PASS; `item`, `Text` and `VERSION` (rule 8) and `_token` (rule 3, a bare annotation)
are UNKNOWN. Rule 7 costs H-uml no row. `fixtures/matrix.json` does not change.

**Plants** (102, `tests/test_cli_python_symbols.py`, rows pinned from an installed 4.0.1): 43
equal, 51 PASS to UNKNOWN, 8 FAIL to UNKNOWN. Six release FAILs are false (`globals-write`,
`dict-instance`, `nested-function`, `ff-attr-*`, `lambda-as-method`). The core never gives PASS
where the truth differs, nor FAIL where it agrees.

**Open** (`docs/known-limits.md`). A write from a C extension or through `globals()` of another
module; a module outside the scan roots.
