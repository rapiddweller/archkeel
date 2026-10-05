# AD-187 Class field assignments retain their sites

Python class assignments define UML attributes even without annotations. Their
names, visibility, static storage and evidence travel through SourceFacts into
the shared graph. Chained and destructured assignments retain distinct identities;
reassigning a name retains both sites. No type is inferred from the initializer.

This does not complete the member inventory. Instance writes and dynamic class
creation remain outside complete proof. Writes to another object's attribute
are not declarations in the writer's class. AD-70's public field inventory still
reads annotated fields only; UML assignment declarations cannot expand it.

The shared renderer underlines static fields and operations in previews and
drill-down. Target and As-Is use the same modifier from the graph.

Proof: `tests/test_static_fields.py`, malformed process metadata in
`tests/test_member_inventory.py`, and native field-shadow controls in
`tests/test_boundary_type_native_payloads.py`.
