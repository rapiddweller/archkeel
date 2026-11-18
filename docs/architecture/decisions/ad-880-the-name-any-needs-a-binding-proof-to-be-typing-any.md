# AD-880 The name Any needs a binding proof to be typing.Any

Status. Accepted. Issue #1833, part of #1537. It replaces the mechanism of AD-874 and keeps its result.

AD-874 hid a name `Any` that a module binds to something else. Two false FAILs stayed: `x: Outer.Any`
with a class `Any` inside `Outer`, and a star import from `typing` followed by a class `Any`. Both
have one origin: the survey took the name as `typing.Any` and looked only for a counter-proof.

The survey now needs a proof (`Binders::names_typing_any`). `any_annotation` is reported only with it.
The rest is UNKNOWN, because the construct is partial (AD-737).

- Name `Any`: each binder of `Any` in the module is an import of `Any` from `typing`, and each star
  import is from `typing`. With no binder at all, at least one such star import must exist.
- Attribute `m.Any`: each binder of `m` is `import typing` (with or without `as`).
- Not proven: another star import, a type parameter list, a second binder of the name, an unbound
  name, a longer attribute chain.

An import under an `if` keeps the proof, because all binders are typing imports. No name is
excepted by its text alone.

**The module itself (review of #1835).** The binders prove the import, not the object. The scan
also needs that nothing replaces `typing` (`ClassWrites::typing_unchanged`, the evidence of AD-782):

- No file `typing.py` or `typing/__init__.py` in the repository root or in a directory where the
  modules of the scan are found (`import typing` would find it first). A file of the scan that has
  no module name is read as a path.
- No store that can change `Any`: an attribute store of that name, a computed name (`setattr`),
  a store through `sys.modules`, `vars`, `__dict__` or `globals`, or code run from a text. The
  files outside the scan roots count; a test file does not (the stated premise).
- No site of the scanned modules changes the import system or runs a door, after the `sys.path`
  forms of AD-538 are settled (`hazards`, AD-450): `sys.modules` in any alias or scope, `sys.path`,
  `site`, `importlib`, `__import__`, `exec`, `eval`, `mock.patch`. A scan with such a site leaves
  the identity of `typing` unproven (UNKNOWN). The same list gives `class_namespace_safe`.
- A run that reports an `any_annotation` states one more sentence of its premise: the module
  `typing` is the one of the standard library and code outside the scan roots leaves `typing.Any`
  unchanged (`TYPING_PREMISE`). The premise covers only code outside the scan; what the scan
  shows is evidence, not premise. A true positive rests on both.

`typing_extensions` is no standard module. Nothing in the scan shows which object it gives
(`typing.Any` from version 4.4 on Python 3.11, its own class before). It is never proven: UNKNOWN.

## Kept gaps

- Any door or import-system site in the scan (for example `importlib.import_module`) gives UNKNOWN
  for each `Any` annotation of the run, even when it cannot reach `typing`. The guard has no
  narrower fact for what a site can replace. A narrower proof needs its own AD.
- A star import from `typing` and a class `Any` in one module is UNKNOWN in both orders. The source
  order decides the object at run time, and the survey does not order the bindings.
- `from lib import Any`, where `lib` re-exports `typing.Any`, is UNKNOWN (AD-874).
- A name without a binder (`x: Any` with no import) was FAIL before and is UNKNOWN now.
- `typing_extensions.Any` was FAIL before and is UNKNOWN now (no basis for the object).
- A test file that replaces `typing.Any`, a name built at run time and a replacement outside the
  repository are the stated premise, not evidence.

Check: `tests/test_cli_python_any_identity.py` runs each plant in CPython and against the release core.
A FAIL is allowed only where CPython says `typing.Any`. It holds the four counter-probes of the review
(a scanned `typing.py` or `typing_extensions.py`, a write through an alias or in another module, a
replacement in `sys.modules`) and a write outside the scan.

Undo: restore the counter-proof of AD-874 in `Binders` and `Walk::annotation`, and drop
`TYPING_PREMISE`.
