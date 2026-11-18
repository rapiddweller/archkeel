# AD-880 The name Any needs a binding proof to be typing.Any

Status. Accepted. Issue #1833, part of #1537. It replaces the mechanism of AD-874 and keeps its result.

AD-874 hid a name `Any` that a module binds to something else. Two false FAILs stayed: `x: Outer.Any`
with a class `Any` inside `Outer`, and a star import from `typing` followed by a class `Any`. Both
have one origin: the survey took the name as `typing.Any` and looked only for a counter-proof.

The survey now needs a proof (`Binders::names_typing_any`). `any_annotation` is reported only with it.
The rest is UNKNOWN, because the construct is partial (AD-737).

- Name `Any`: each binder of `Any` in the module is an import of `Any` from `typing` or
  `typing_extensions`, and each star import is from one of them. With no binder at all, at least
  one such star import must exist.
- Attribute `m.Any`: `m` is a name, and each binder of `m` is `import typing` or
  `import typing_extensions` (with or without `as`).
- Not proven: another star import, a type parameter list, a second binder of the name, an unbound
  name, a longer attribute chain.

An import under an `if` keeps the proof, because all binders are typing imports. No name is
excepted by its text alone.

## Kept gaps

- A star import from `typing` and a class `Any` in one module is UNKNOWN in both orders. The source
  order decides the object at run time, and the survey does not order the bindings.
- `from lib import Any`, where `lib` re-exports `typing.Any`, is UNKNOWN (AD-874).
- A name without a binder (`x: Any` with no import) was FAIL before and is UNKNOWN now.

Check: `tests/test_cli_python_any_identity.py` runs each plant in CPython and against the release core.
A FAIL is allowed only where CPython says `typing.Any`.

Undo: restore the counter-proof of AD-874 in `Binders` and `Walk::annotation`.
