# AD-183 Target references bind declarations

Bind Target references to one planned definition in the authenticated contract tree.
References carry identity and provenance, not duplicate signatures, fields or
responsibilities. No definition leaves an external reference; ambiguous owners and
hidden constraints are errors. Bound references cannot own completeness scopes.

Core records entities and relationships from the compiled graph, never mixing raw
endpoints with compiled identities. The linker reads no Analyzer facts, preserving
independent Target intent.

[Linker proof](../../../tests/test_target_reference_linking.py).
