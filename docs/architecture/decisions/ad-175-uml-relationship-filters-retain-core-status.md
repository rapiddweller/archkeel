# AD-175 UML relationship filters retain Core status

The UML legend selects one relationship kind or all kinds. It uses the same
scene filter in As-Is, Target and Diff. Focus shows neighbors for the selected
kind; without Focus, every element remains visible.

Counts name the subset and complete level. Hidden edges have no hit areas.
Opening an element clears the filter; Back restores it. View switching and
Reset use the existing state and controls.

Filtering changes no graph, evidence or Core verdict. Details retain all sites;
Diff retains its complete status and unlisted-relationship notice. Dense graphs
still need layout work. A type filter does not prove clean routing.

The router checks arrival stems against cards and tries shorter clear stems
before choosing a detour. This fixes a card intersection and a shared stretch
in the own ArchitectureGraph call view. Other dense layouts remain unproven.

Proof: `tests/test_uml_visual_acceptance.py` checks all three views, keyboard use,
hidden hit areas, restored identities, complete evidence and a filtered Core FAIL.
`tests/test_own_uml_target.py` checks the dense call view and actual arrow endpoints.
