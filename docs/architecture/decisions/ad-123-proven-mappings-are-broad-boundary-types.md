# AD-123 Proven mappings are broad boundary types

Treat proven standard-library `Mapping` and `MutableMapping` like `dict`:
key and value annotations do not declare record fields. Bare mappings also produce
broad-type findings. Resolve members independently, retaining violations and UNKNOWN.

Allowances select exact positions, annotations and container depth; they cannot
exempt siblings or member findings. Malformed or unresolved bindings remain UNKNOWN.
Existing fingerprints may gain occurrences, so review baselines before accepting
increased debt with `--write-baseline --accept-new`.

[Mapping proof](../../../tests/test_boundary_types_mappings.py).
