# AD-171 Static values retain their assignment sites

The Python call collector records direct call-result assignments and constructor
candidates. It receives no Target or rule policy. The unread-binding collector
keeps its existing meaning. No second instance section or collector is added.
The published Source IR schema checks these optional call fields. Old call
records remain readable.

The shared graph uses `binding` entities with initializer syntax, lexical parents,
annotations and source evidence. Existing namespace bindings retain their IDs.
`creates` and `instance_of` retain the original call record. Chained assignment
has two bindings and one construction site. Rebinding keeps separate sites.

A direct, stable module class name with inert declarations, default allocation
and default initialization can establish the nominal result type. Qualified
constructor access stays partial. Visible lexical shadowing
prevents borrowing a module class. Custom allocation, initialization, bases,
metaclasses, decorators and class-body execution retain candidates. Attribute
storage remains partial. A factory result or annotation proves no construction.
Runtime execution, live identity, lifetime and the current value are unobserved.

Core compares independent initializer and instance intent. The common renderer
shows underlined binding names, initializer syntax, directed relationships and
evidence in As-Is, Target and Diff. Coverage stays partial. Older snapshots without
these call facts remain unavailable. Unpacking, other binding forms, complete
lexical resolution and explicit SourceFacts capabilities remain open.

PR #277's SourceFacts/Core and process-port direction is unchanged.
Proof: `tests/test_static_instances.py`, `tests/test_uml_rendering.py`;
`make check`, `make report-browser`, `make self-observation`, `make self-validate`.
