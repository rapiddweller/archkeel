# AD-132 Datetime is a proven boundary scalar leaf

Accept exactly proven `datetime.datetime` as an imported scalar leaf, using the
shared annotation resolver. Explicit imports, aliases and module members need stable,
unshadowed bindings; spelling alone proves nothing.

Rebinding, member writes or deletes, star imports and uncertain declaring scopes
retain UNKNOWN, including inherited annotations. External effects are not executed.
Other external types remain UNKNOWN and `object` remains broad. Mappings reuse the
binding proof without becoming scalar leaves.

[Datetime proof](../../../tests/test_boundary_types_datetime.py).
