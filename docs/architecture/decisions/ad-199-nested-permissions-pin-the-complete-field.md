# AD-199 Nested permissions pin the complete field

Match nested permissions against the complete field declaration, not one union
member. Correlate declarations and findings before deduplication; parent paths
must retain leaf annotations and proven Optional spelling.

Resolve one declaration before selecting members or depth, including clean and
UNKNOWN declarations. One compound-field allowance selects one outer map.
Ambiguous same-path fields, aliases and multiple maps stay unallowed; neighboring
findings and UNKNOWN survive. Facts retain selected members; IDs stay stable.

[Field-selector proof](../../../tests/test_boundary_type_nullable_fields.py).
