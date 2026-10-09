# AD-212 Native DTO values use exact field and depth

Combine the existing `field_path` and `container_depth` selectors: the complete
field declaration proves which field is governed; the existing map occurrence
and native-value evidence prove which leaf. Count containers from the signature.

Require one declaration, one alias-free map and one matching native occurrence
before deduplication. Keep outer-map permission separate. Sibling findings and
UNKNOWN survive; accepted opacity is not type closure. Existing selectors, IDs
and widening semantics remain unchanged.

This extends AD-95/142/199/203 without general alias or container support.
[Proof](../../../tests/test_boundary_type_dto_native_values.py).
