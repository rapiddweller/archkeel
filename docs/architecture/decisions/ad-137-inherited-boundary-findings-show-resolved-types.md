# AD-137: Inherited boundary findings show resolved types

Inherited findings retain raw annotations and append already-proven concrete
origins in `resolved_types`. Reporting only `T` hid the model needing publication;
rewriting it would lose source evidence. Reuse the substituted verdict rather than
resolve again.

IDs, fingerprints, subjects and source evidence stay unchanged. The origin list
includes all proven reached types, including fields; it does not guess a single
culprit. Ambiguous substitution remains UNKNOWN without invented origins.

[Diagnostic proof](../../../tests/test_inherited_boundary_diagnostics.py).
