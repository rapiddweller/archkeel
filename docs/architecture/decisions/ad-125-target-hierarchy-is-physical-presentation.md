# AD-125: Target hierarchy is physical presentation

Use `root_layout` frames to present physical placement alongside semantic Target
components. Frames create no owners, permissions or architectural layers.
Placement uncertainty stays explicit; semantic requirements determine dependency order.
Cycles retain all nodes and edges, without calling every unranked dependent cyclic.

Diagram frames require uniquely placed observed modules. Target-only components,
absent children, permission edges and ranks cannot become observed evidence.
Declared empty cards prove no existence; Diff retains absent declarations.
Rendering and routing warnings never change verdicts. Details retain full identity,
responsibility and provenance when labels are shortened.

[Target graph proof](../../../tests/test_target_graph.py).
