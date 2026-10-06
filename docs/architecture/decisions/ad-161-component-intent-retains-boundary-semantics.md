# AD-161 Component intent retains boundary semantics

Record component intent separately from source entities: role, ownership, namespace,
published/planned API, exclusions, decider and inner boundary. Each immutable record
has one declared component owner; observed graphs cannot carry Target intent.

API membership is distinct from language visibility. Absent and explicitly empty
remain different; planned selectors invent no classes or calls. Core authenticates
owner metadata against declarations. Existing role exports and contract encoding
remain compatible.

[Target proof](../../../tests/test_target_graph.py).
