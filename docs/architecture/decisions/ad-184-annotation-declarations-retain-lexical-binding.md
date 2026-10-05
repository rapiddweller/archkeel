# AD-184 Annotation declarations retain lexical binding

Python resolves an operation's header in its enclosing scope. A parameter or return
annotation belongs to the operation's signature. These are separate identities.

The reference collector retains `source_scope` and `source_definition_id` for lexical
resolution. Parameter and return annotations also record `declaration_scope` and
`declaration_definition_id`. Defaults, decorators and ordinary reads keep lexical ownership.

IR validates the optional pair against one recorded method/function definition site.
The UML reference uses that operation as its source. Legacy records keep their old scope.
This changes no name binding, candidate resolution, architecture policy or coverage claim.
The Python profile schema requires both fields together. The SourceFacts codec rejects
wrong field types, empty identities and a declaration outside the reference's module.

Proof: `tests/test_source_graph.py`: class shadowing, async and repeated operations,
defaults, legacy records and malformed identities.
