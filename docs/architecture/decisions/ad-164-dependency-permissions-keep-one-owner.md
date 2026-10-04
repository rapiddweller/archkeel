# AD-164 Dependency permissions keep one owner

`requires` permits component imports. It does not require an import or call.
The existing Core dependency rules own its verdict.

Independent and canonical Target producers derive the same permission relationships
from existing component declarations. Each retains `through`, rationale, provenance
and the effective decider. Entry approval overrides the component's default.
Identities survive reordering; distinct slices and duplicate entries remain separate.

Core authenticates permission contents against the independent contract tree.
The canonical UML target references component records; it copies no permission list.
Explicit UML declarations cannot redeclare `requires` or use it as a completeness kind.
The UML comparator skips permissions. This avoids a second policy owner.

Target and Diff use the shared dependency renderer. Details names the allowed import,
its selectors and decider. Selection retains every declaration site in the displayed edge.
No analyzer parsing, policy or port changed.

Proof: `tests/test_target_graph.py`, `tests/test_architecture_graph.py`,
`tests/test_uml_comparison.py` and `tests/test_uml_rendering.py`.
