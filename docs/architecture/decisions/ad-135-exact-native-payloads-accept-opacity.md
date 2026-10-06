# AD-135 Exact native payloads accept opacity

Accept native payload opacity through an exact callable, position, root path and
`object` or `object | None` annotation. JSON narrowing changes behavior; wrappers add no evidence. Input acceptance cannot permit returns or
other methods, and nullable annotations require their own match.

Allowance evidence records `accepted_opacity: true` and decision provenance.
Type closure remains unproved; uncertain bindings stay UNKNOWN. Adding permission
requires widening approval. Bare mappings retain their separate restriction.

[Native-payload proof](../../../tests/test_boundary_type_native_payloads.py).
