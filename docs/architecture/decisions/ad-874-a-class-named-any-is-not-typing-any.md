# AD-874 A class named Any is not typing.Any

Status. Accepted. Part of #1537. It amends AD-737 (the `any_annotation` construct).

The survey took each `Any` name in an annotation as `typing.Any`. A module with `class Any: pass`
and `x: Any = None` then got a forbidden `any_annotation`: a wrong FAIL.

The survey now counts the binders of the name `Any` in the module (`Binders::count`) and the
imports of `Any` from `typing` or `typing_extensions` among them. When a binder is not such an
import, the name is local and gives no `any_annotation`. The construct is partial (AD-737), so the
rule reads UNKNOWN there and not PASS. A star import makes the count unknown: the name stays as
before. `x.Any` is not changed.

## Kept gaps

- A function-local binder of `Any` also makes the module-level name local (UNKNOWN, not FAIL).
- A module that both imports `typing.Any` and defines a class `Any` gives UNKNOWN.

Undo: remove `Binders::any_is_local` and its use in `Walk::annotation`.
