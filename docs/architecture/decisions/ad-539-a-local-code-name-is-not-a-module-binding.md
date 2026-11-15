# AD-539: A local `code` name is not a module binding

## Decision

A local name `code` is not the standard-library module by its spelling alone. The collector
keeps a dynamic-import gap when an import binds the name, when a star import or delete makes
the binding uncertain, and in a class body. It keeps a gap on `provider.code` when `provider`
is import-bound. It keeps the existing literal-import edge and other loader gaps.

The import bindings are collected for the whole file. A binding in another scope can still
cause a false gap. This conservative limit needs the scope facts before the gap can be removed.
The collector does not follow a value from an unknown object: `code = provider.code;
code.interact()` has no gap when `provider` is unknown. A forbidden dependency through that
value can give PASS. This is an open false-PASS class, not an accepted limit.

## Reason

A parameter or local named `code` is common and need not be a module. Treating each as a loader
keeps unrelated import rules UNKNOWN. A star import, a delete, or a class body makes the binding
uncertain, so the collector must not clear the gap there.

## Alternatives

Keeping the spelling rule preserves false gaps. Treating all attributes named `code` as safe can
miss a module reached through an imported provider. Full scope and value-flow resolution is not
part of this change.

## Verification

`native/python/src/survey/hazards_tests.rs` has plants for local names, unknown objects, imports,
star imports, deletes, class bodies, imported providers and import-system writes.
