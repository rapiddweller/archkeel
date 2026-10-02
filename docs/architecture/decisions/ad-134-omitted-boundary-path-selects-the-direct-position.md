# AD-134 Omitted boundary paths select the direct position

Issue #207 needs an exact `return: dict[str, str]` allowance for caller-defined
property names. AD-123 already matches that position with `field_path: ""`.
The remaining gap was a mandatory JSON field.

Omission now normalizes to the existing empty path in the shared parser:

```json
{"qualified_name": "sample.app.impl.run", "position": "return", "annotation": "dict[str, str]"}
```

The matcher and canonical writer stay unchanged. Existing contracts keep their
bytes and digests; replacing an empty path with omission is not widening.
Adding either selector still requires an amendment under `--against`.

Nonempty paths keep nested semantics. Malformed entries, unknown fields,
normalized duplicates and bare broad annotations remain rejected. A direct
allowance never hides inputs, other functions, nested fields or UNKNOWNs.
Keeping the field mandatory would retain the issue; a second matcher would
duplicate AD-123 without adding behavior.

`tests/test_boundary_type_direct_defaults.py` checks normalization and negative
neighbors. `tests/test_widening.py` checks comparisons. The `direct-default`
and `direct-neighbors` catalog variants produce ordinary JSON/HTML evidence.
