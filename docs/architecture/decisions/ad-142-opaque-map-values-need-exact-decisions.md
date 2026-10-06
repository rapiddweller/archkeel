# AD-142 Opaque map values need exact decisions

Use positive `container_depth` to accept one literal opaque map value.
Bind the callable, position and full signature; outer-map permission needs a separate
entry. Collections and maps increase depth; unions do not.

Select one pathless, alias-free mapping before deduplication. Ambiguity,
object keys and named DTO routes cannot match. UNKNOWN neighbors remain visible;
accepted opacity proves no closure. Omitted depth preserves existing bytes and behavior;
adding or changing it requires widening approval.

[Opaque-value proof](../../../tests/test_boundary_type_opaque_map_values.py).
