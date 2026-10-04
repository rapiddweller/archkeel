# AD-168 Global API intent keeps its declaration evidence

`ArchitectureGraph.public_api` retains each global contract selector as a frozen
`PublicAPIEntry`: existing declaration ID, selector and independent provenance.
The generated schema and strict codec use the same dataclass. Older graph payloads
without this field remain readable.

Core authenticates selectors and provenance against the held contract. Its Target
descriptor references canonical declaration IDs. Independent and recorded Target
producers agree, including set-like ordering. API-only contracts also publish a
graph. Existing API identities, rules and assessments keep their meaning.

The legacy declaration's source-derived `types` field does not enter Target intent.
A selector does not define a class, signature or language visibility. Explicit UML
intent still owns those declarations. No API existence rule is added.
Missing provenance remains an error. Global API declarations remain unsupported
inside an inside contract; they cannot silently become component API intent.

Shared UML Target and Diff Details show global API intent at the root scope.
Legacy browser migration and source capabilities remain open. PR #277's adapter
and process protocol are unchanged; the existing API identity function moved to IR.

Proof: `tests/test_target_graph.py`; `tests/test_architecture_graph.py`;
`tests/test_uml_rendering.py`.
