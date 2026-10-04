# AD-174 UML focus retains complete evidence

The existing Focus control also filters standard UML scenes. It selects one exact
entity ID and draws its incoming and outgoing neighbors. All typed connections
between that entity and its neighbors remain visible, including uncertain sites.

Counts show the focused subset and the complete level. Reset restores the level;
back navigation and view switching retain the chosen focus. Hover changes styling
only. An isolated entity has no connection hit areas.

This is a rendering filter. It changes no graph values, evidence, Target intent,
Core assessment or verdict. Diff keeps its complete Core status visible.
Large neighborhoods can still be unreadable; focus is not a global layout proof.

Proof: `tests/test_uml_visual_acceptance.py` exercises Source, Target and Diff,
an unrelated classifier, a Core FAIL, actual route geometry and restored identities.
