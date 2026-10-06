# AD-175 UML relationship filters retain Core status

Filter UML by relationship kind through the shared scene in all views.
Focus follows neighbors of the selected kind; otherwise keep every element.
Counts disclose hidden edges, which have no hit areas. Navigation and Reset
restore the recorded selection.

Filtering changes no graph or Core verdict. Details retain all sites and Diff's
complete status. Selecting a kind cannot prove clean routing in dense graphs.

[Filter proof](../../../tests/test_uml_visual_acceptance.py).
