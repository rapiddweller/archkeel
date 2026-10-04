# AD-177 UML element filters retain complete evidence

As-Is, Target and Diff select element kinds from the standard graph. The shared
scene keeps matching cards and connections with two visible endpoints. Counts
name the subset and complete level. Details and Core verdicts stay complete.

The filter uses existing navigation state. Opening an element clears it; Back
and view switching restore it. Reset restores every identity. Hidden elements
and connections have no hit areas. No graph, rule or evidence changes.

If the router cannot avoid a shared stretch, it retries with additional lanes
and arrival heights inside the existing row gap. Other routes keep the first
search. This clears reproduced overlaps in the own As-Is class overview without
expanding every route search. The retry requires measured cards to fit within
the canvas area; larger levels keep the first search and need filtering. Large
complete overviews still need layout work.

Proof: `tests/test_uml_visual_acceptance.py` checks all views and retained Core
FAIL. `tests/test_own_uml_target.py` checks actual own-model routes and UML glyphs.
