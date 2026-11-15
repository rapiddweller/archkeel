# AD-552: A literal binding is not a module object

## Status

Accepted for the Python import survey. This decision refines AD-504.

## Decision

A plain literal or display creates a value that is not a module object.
The `type` statement also creates a type alias object, not a module.
Subscripts of the builtin generic types create generic aliases, not modules.
The survey requires the generic name to have no module-level binding.
Selected `typing` factories also create non-module values.
The survey admits them only when their scanned uses cannot change the factory.
Their arguments must be literals or unbound builtin types.
An attribute write anywhere in the scan blocks this factory proof.
The survey can use that fact when an imported name is used as a value.
The binding must be the only plain module-level binding of that name.
The survey follows a unique plain re-import to its origin, with a depth limit.

A star import, `__getattr__`, a namespace hazard or an attribute write blocks this proof.
A different dynamic-import hazard keeps its own named gap.
A scanned submodule with the same name also blocks the proof.
Other calls and expressions remain unknown. The survey keeps their escape.
An annotation of `TypeAlias` alone does not prove the value kind.
Other subscript heads can return a module and remain unknown.
The survey does not use an origin outside the scan as proof.

## Reason

An imported literal cannot itself be a module object.
Treating every imported literal as a possible module withholds unrelated routes.
A submodule can replace a package attribute after the package is imported.
Multiple bindings and runtime namespace changes can also replace the value.
The survey therefore keeps the escape when it cannot exclude these cases.

## Checks and limits

`survey/uses_tests.rs` checks literal and display values, re-imports and refusal cases.
The existing depth bound keeps cycles and long chains unknown.
Dynamic namespace changes and code outside the scan retain the limits in
`docs/known-limits.md`. A gap remains a gap; this decision does not close it.
