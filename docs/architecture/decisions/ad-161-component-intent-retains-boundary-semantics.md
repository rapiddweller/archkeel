# AD-161 Component intent retains boundary semantics

`ArchitectureGraph.component_intents` records component roles, ownership selectors,
namespace, published and planned APIs, excluded responsibilities, decider and inner contract.
Each immutable `ComponentIntent` names exactly one declared component. The graph rejects
duplicates, missing owners, classifier owners and observed graphs carrying this intent.

API membership is separate from language visibility. `None` means not declared; an empty
tuple means explicitly empty. A planned API selector does not invent a class or a call.
Module inventories and physical layout permissions use separate graph fields (AD-162).

The independent contract producer and canonical-record producer retain the same component intent.
Core authenticates these owner fields against the declaration revision before comparison.
The existing adapter projection now retains `planned` and inner component roles; no new
policy or graph assembly is added to the adapter. Its removal belongs to PR #277's Core assembly.

`ComponentRole` has one definition in `ir.architecture_graph`; `ir.model.ComponentRole` remains a compatible
export. Enum placement names both IR model modules. This changes vocabulary ownership,
not measurement budgets. Contract 2.1 JSON encoding remains unchanged.

The common renderer shows role on component cards and boundary intent in Details.
Proof: `tests/test_target_graph.py`, `tests/test_uml_rendering.py` and schema round trips.
