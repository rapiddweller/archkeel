# AD-218 Native Iterable elements use proven signatures

For [issue #443](https://github.com/rapiddweller/archkeel/issues/443), an exact
direct `Iterable[object]` signature, optionally unioned with `None`,
can accept one native element using the existing `allowed_positions` fields:
qualified callable, position, complete annotation, empty field path and
`container_depth: 1`. Type shapes and unique standard `typing` or
`collections.abc` bindings must prove the container and builtin `object`.

Keep that proof private to the direct annotation. Aliases, DTO fields,
wrappers, other collections, unknown bindings, extra union arms and repeated
opaque leaves do not qualify. The fact retains accepted opacity, provenance
and evidence; it proves no serialization, materialization or type closure.
Existing mapping grants, findings, UNKNOWNs and amendment widening stay intact.
[Proof](../../../tests/test_boundary_type_native_iterables.py).
