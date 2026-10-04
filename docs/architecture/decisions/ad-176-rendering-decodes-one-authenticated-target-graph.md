# AD-176 Rendering decodes one authenticated Target graph

Report rendering decodes the root Target graph once. The UML payload and the
legacy physical projection receive the same graph. Component roles and import
permissions use its identities, endpoints and declaration evidence.

Each permission remains selectable, including repeated declarations with the
same endpoints. Observed calls and references may still aggregate source sites.

Explicit UML uses the standard graph scene. Legacy file and layout navigation
keeps its compatibility projection until that navigation can be migrated without
losing inventory or existing Diff findings. Publishing the graph adds no UML
rule, comparison or verdict to a legacy contract.

Proof: `tests/test_legacy_graph_rendering.py` checks both contract versions,
nested scopes, one decode, distinct permissions, focus and retained Diff data.
