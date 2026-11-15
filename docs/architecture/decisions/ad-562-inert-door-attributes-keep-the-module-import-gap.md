# AD-562: Inert door attributes keep the module import gap

## Status

Accepted for the Python import survey. This decision refines AD-450.

## Decision

The survey does not add a second dynamic-import gap for a direct load of a
listed inert attribute from a uniquely bound, directly imported module.
The module import still has its own dynamic-import gap. This gap also covers
uncertainty about the module and its runtime mutation.

A store, a deeper chain or an ambiguous binding is not exempt under this rule.
Other attributes keep their existing treatment.
The same name bound by a parameter, a second import, a star import or a local
assignment is ambiguous. The survey keeps its gap.

## Reason

The admitted names are `pickle.UnpicklingError`, `pickle.PickleError`,
`pickle.HIGHEST_PROTOCOL`, `importlib.metadata.PackageNotFoundError` and
`importlib.abc.Traversable`. Their standard values are not loader functions.
An actual `pickle.loads` can import a module named by its input.
`pickle.dumps` can run a reducer that imports a module. It keeps its gap too.
`importlib.resources.files` can import its package argument and keeps its gap.

## Checks and limits

`survey/hazards_tests.rs` checks the direct read, its import gap and the unsafe
neighbor forms. A real Python plant confirms that the exception read adds no
module and that `pickle.loads` can import a module.
This decision does not prove that an arbitrary replacement for `pickle` is safe.
Do not remove the import gap without a separate proof of the module binding.
