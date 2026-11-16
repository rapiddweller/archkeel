# AD-690: A dill settings read keeps the import gap

## Status

Accepted for the Python import survey. This extends AD-574.

## Decision

A direct load of `settings` on a uniquely bound, directly imported `dill` module gets no
second dynamic-import gap. The import of `dill` keeps its gap, which covers uncertainty about
the module and its replacement or mutation. A store to `dill.settings` itself, a deeper
attribute chain or an ambiguous binding does not use this rule. A subscript store through
the loaded value still has the import gap.

## Reason

The standard `dill.settings` value is a dictionary. A Python 3.12 plant with dill 0.4.0 reads
its `protocol`, `byref`, `fmode` and `recurse` entries without importing a module. A replacement
can run code, so the module import gap must stay. `dill` serialization and unpickling remain
doors.

## Checks

`survey/hazards_tests.rs` checks direct and aliased reads, the retained import gap, stores,
rebinding, a star import and a deeper chain. Python 3.12 plants check the dictionary and a
replacement whose lookup imports a module.
