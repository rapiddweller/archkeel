# AD-134 Omitted boundary paths select the direct position

Normalize omitted `field_path` to the existing empty path for direct boundary
positions. Requiring an explicit empty string added no selector behavior.
The matcher, canonical bytes and digests remain unchanged; replacing empty with
omitted is not widening. Adding either allowance still is.

Named paths keep nested semantics. Malformed entries, unknown fields, normalized
duplicates and bare broad annotations remain invalid. A direct allowance cannot
hide neighboring positions, nested fields or UNKNOWN.

[Normalization proof](../../../tests/test_boundary_type_direct_defaults.py).
