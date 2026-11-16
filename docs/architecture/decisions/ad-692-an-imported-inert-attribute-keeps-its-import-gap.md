# AD-692: An imported inert attribute keeps its import gap

## Status

Accepted for the Python import survey. This extends AD-574 and AD-690.

## Decision

For a uniquely bound direct import of an attribute already listed by those decisions, the survey
does not add a second gap for a bare load of the imported name. The import itself keeps its
dynamic-import gap, with no declared-reach door form. A rebound or ambiguous name, a store,
and attribute chains retain their existing treatment. The rule applies only when the import
itself produces a hazard gap.

## Reason

The retained import gap covers uncertainty from replacement or mutation of the imported object.
It also covers code run by a use of that object. Python 3.12 confirms that an ordinary
`Traversable` annotation imports no new module, but a substituted object can import one.

## Checks

`hazards_inert_tests.rs` covers direct and aliased imports, the retained import gap, rebinding,
a star import, a deeper chain and existing inert pickle and dill attributes.
