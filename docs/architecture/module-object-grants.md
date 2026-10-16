# Exact module-object grants

Contract 3.6.0 adds an optional `module_object_grants` array to
`interface_boundary`. It allows a composition registry to receive a package
object for discovery while the owning component keeps its existing named
`public` inventory.

```json
{
  "id": "INTERFACE",
  "kind": "interface_boundary",
  "module_object_grants": [
    {"source_module": "demo.registry", "target_module": "demo.plugins"}
  ],
  "rationale": "The registry discovers plugins; consumers use named public APIs.",
  "provenance": ["docs/architecture.md"],
  "decided_by": "architect"
}
```

For example, with plugins published only as `demo.plugins:Allowed`,
`import demo.plugins as plugins` is allowed in `demo.registry`. The equivalent
resolved relative import and a local alias have the same exact identities.
A module below either endpoint receives no permission from this grant.
Other callers still cannot import the package object.

The grant applies only when native evidence proves the import refers to a module
object: `symbols_known` is true and `symbol` is null. It does not publish
`Secret`, private names, wildcard imports, or a same-owner forwarder's
unpublished names, even to the registry. Named imports continue to use the one
component `public` list and the existing publication-route checks. Publishing
an entire module retains its existing wider meaning; a grant does not require
doing so.

The grant changes only the interface verdict. Forbidden dependencies, complete
requires, type-checking scope, export validation and other policies still apply.
It does not declare an allowed component pair. Dynamic attribute access,
`vars`, reflection and runtime loading after obtaining the object are outside
this import proof. Dart and TypeScript profiles reject requested grants because
they do not provide the required module-object proof.

The wire shape accepts exact dotted module names and no other keys, prefixes,
modes or symbols. Duplicate grants are invalid. Both endpoints participate in
normal namespace validation and package renames, including mounted contracts.
Adding a grant or changing an endpoint is widening; removing a grant is
narrowing. Earlier contract versions reject the field, including an empty array.
Omitting it preserves historical canonical bytes; an authored empty array
roundtrips as empty.

The model owns frozen `ModuleObjectGrant(source_module, target_module)` values.
`InterfaceBoundaryRule.module_object_grants` is
`tuple[ModuleObjectGrant, ...] | None`. Five independent declarations in the own
IR Target pin the class, both identity fields, the owning rule and this field.
Native tests retain that Target while widening the Python field annotation to
`str | None`; the mismatch produces a trace-valid failure. This bounded intent
does not close the remaining model inventory or activate a broader model type
boundary.
