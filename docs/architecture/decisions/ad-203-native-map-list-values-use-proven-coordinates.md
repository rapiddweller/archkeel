# AD-203 Native map list values use proven coordinates

Select opaque `dict[str, list[object]]` values with proven `container_depth: 2`,
using existing mapping and builtin-binding evidence. Exact callable, position,
complete annotation, one alias-free map and one opaque occurrence remain required.
The outer map needs its own permission.

Shadowed names, aliases, ambiguous leaves and unsupported shapes grant nothing.
Sibling findings and UNKNOWN remain. Facts record accepted opacity and provenance,
never type closure. This adds no selector or wire format.

[List-value proof](../../../tests/test_boundary_type_native_map_lists.py).
