# AD-183 Target references bind declarations

A Target module can reference a type or operation declared by another inside contract.
The reference carries identity: language, kind, qualified name and optional lexical owner.
It carries no duplicate signature, fields or responsibilities.

IR binds it to one planned definition after compiling the authenticated contract tree.
The compiled graph keeps one entity identity and preserves reference provenance.
No definition leaves an external reference. Ambiguity, conflicting owners and hidden
constraints are errors. Referenced entities cannot own completeness scopes when bound.

Core records entities and relationships from that compiled graph. It does not combine
compiled entities with raw relationship endpoints. The linker reads no Analyzer facts.

The SourceCollector Target adds its interface, operation, immutable request/response/facts
fields and bounded ProcessCollector methods. It is independent of the observed graph.
Inventory completeness still requires better source evidence. AD-184 separates annotation
declarations from their Python evaluation scopes.

Proof: `tests/test_target_reference_linking.py`, including authenticated nested contracts.
