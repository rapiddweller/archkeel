# AD-722: Imported code types in isinstance retain their import gap

## Status

Accepted for the Python import survey. This extends AD-574.

## Decision

A uniquely bound, direct top-level import of `types.FunctionType` or `types.CodeType`
keeps its non-declarable every-module import gap. A bare, unshadowed `isinstance` call
with that name as its second positional argument adds no duplicate gap for the name.
The first argument is still surveyed. Calls that construct code, aliases, rebinding and
other uses keep their gaps.

## Reason

The import gap already covers the unknown code of every module, including mutation of the
imported value. This is not a claim that `isinstance` is inert: Python 3.12 can run an
operand's `__class__` property and import another module.

## Checks

`hazards_inert_tests.rs` checks both names, the retained import gap, an operand with an
`eval` door, constructors, aliases, rebinding and star imports.
