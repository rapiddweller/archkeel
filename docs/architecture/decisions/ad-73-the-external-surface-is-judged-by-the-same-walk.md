# AD-73 The external surface is judged by the same walk

## What changes

[AD-70](ad-70-the-external-promise-declares-every-type-it-hands-out.md) held by hand: one test
pinned the three names `archkeel.api` happened to promise. The analyzer now resolves what each
`declarations.public_api` entry exposes and publishes it on the entry's own record; `check`
subtracts that from the declared set and resolves nothing itself.

| Entry's signature | Before | Now |
|---|---|---|
| `-> UndeclaredType` | silent | `api_surface.missing` |
| `(x: UndeclaredType)` | silent | `api_surface.missing` |
| `Row.field: UndeclaredType` | silent | `api_surface.missing` |
| `-> tuple[UndeclaredType, ...]` | silent | `api_surface.missing` |
| `-> Path`, `-> tuple[Declared, ...]` | silent | silent |

## Why

An invariant nothing enforces is a comment. `def load_violations(...) -> InternalResult` would
have passed, and the one test that could have caught it names three strings.

Two things had to be true at once, and the second is why this is its own record:

**`check` may not resolve anything.** It cannot import the analyzer (AD-9), so the obvious move
is to reimplement resolution there -- which was written, and rejected: it would be a third
reading of an annotation in the series that removed the second
([AD-69](ad-69-one-annotation-is-read-once-for-both-readers.md)). The answer travels as a
record instead, the way `facade_types` already does (AD-2, AD-4).

**One walk, not two.** Resolving directly missed a type inside a collection. Measured: removing
`archkeel.api:ViolationRow` from `public_api` while `load_violations` returns
`tuple[ViolationRow, ...]` was reported by nothing -- the shape AD-70's own example uses. The
external reader now reads `_boundary_type_verdict`'s walk, so it sees exactly what the internal
rule sees, and stays silent on exactly what the rule stays silent on.

A declared entry is resolved to its origin too: `archkeel.api:ViolationRow` names a type defined
in `archkeel.ir.baseline`, so comparing a resolved origin against a declared string only worked
when a name was declared where it was defined.

## Rejected

| Alternative | Why not |
|---|---|
| Resolve inside `check` | A third reading of an annotation, in a component forbidden to know how. |
| Declare `api.public` and reuse `facade_types` | Nothing imports `archkeel.api` internally, so every entry would be `interface.unused` -- the reason `public_api` exists (AD-66). |
| Compare declared strings literally | Silently passes any type declared at a re-exporting facade. |
| Report a type whose module was never scanned | A builtin, stdlib or third-party type is not a promise a scanned package makes about itself. |

## Limit

A class contributes only its own annotated class-body attributes; a field assigned in
`__init__` is invisible. The shapes AD-67 leaves undecidable -- a union, a mapping, a nested
subscript, a dotted name, a forward reference -- are undecidable here too, by construction:
the two readers must agree, including on silence.

## Check

`tests/test_public_api_boundary.py` covers a return, a parameter, a class attribute and the
builtin/declared-collection guard. `tests/test_self.py::test_self_public_api_declares_every_type_it_hands_out`
holds Archkeel's own surface to it. The structural test in `tests/test_analyzer.py` fails if a
second function ever resolves a name again.
