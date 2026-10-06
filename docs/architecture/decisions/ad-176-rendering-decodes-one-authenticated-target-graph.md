# AD-176 Rendering decodes one authenticated Target graph

Decode the authenticated root Target graph once per report and share it across
UML and physical projections. Roles and permissions retain the same identity,
endpoints and declaration evidence; repeated permission declarations stay selectable.

Explicit UML uses the standard scene. Legacy physical navigation retains its
compatibility projection without losing inventory or Diff findings. Publishing a
graph for legacy declarations adds no UML rule, comparison or verdict.

[Shared-decode proof](../../../tests/test_legacy_graph_rendering.py).
