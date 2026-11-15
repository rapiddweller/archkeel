# AD-566: A call of a bare class or a builtin value type is no module

## Status

Accepted for the Python import survey. Part of #880. It refines AD-504 and AD-552.

## Decision

The survey withholds a route through a module when a scanned module uses an imported name that may be a module object.
These values are not module objects, so their bare use does not withhold the origin module:

- A call of an unbound builtin value type: `list`, `dict`, `tuple`, `set`, `frozenset`, `int`, `str`, `float`, `bool`, `bytes`.
- Arithmetic over number literals.
- A call of a plain name that is a class of the scan with no base, no keyword and no `__new__` in its body.
  Each decorator of the class must be `dataclasses.dataclass`, imported by one plain import.
  The name may be re-imported by plain imports, with the depth bound of AD-552.

The class proof needs one more fact of the whole scan.
No statement of the scan may store or delete `__new__` or `__class__`, call `setattr` or `delattr`, or use `__setattr__` or `__delattr__` on anything but `object`.
`object.__setattr__` raises `TypeError` on a class.
One such statement withholds the proof of every instance.
The proof also needs the origin module to be free of the hazards of AD-504 and AD-552.

Python 3.12 gives an instance, a `frozenset`, a `tuple` or an `int` for each admitted form.
It gives a module for a class with a metaclass `__call__`, a `__new__` that returns a module, or a patched `__new__`.
These forms keep the escape.

## Kept gaps

A class with a base, a keyword or a `__new__`, an unknown decorator, a call of a function, a call of a name from outside the scan, a rebound builtin and a conditional class keep the escape.
The proof does not read the bases of a scanned class.
An external base such as a Pydantic model may use a metaclass that the code cannot show.

## Checks and limits

`uses_construct_tests.rs` has the admitted forms and each kept form.
Subscript aliases such as `Annotated[X, Field(...)]` and unions of imported types stay escaped.
AD-552 withholds the typing factory proof when any attribute store exists in the scan.
That condition is true in every real project and is not changed here.
