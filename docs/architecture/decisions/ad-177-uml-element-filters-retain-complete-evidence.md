# AD-177 UML element filters retain complete evidence

Filter UML element kinds through the standard graph in all views.
Keep matching cards and only connections with two visible endpoints.
Show subset and complete-level counts; Details and Core verdicts remain complete.

Navigation restores filter state, and Reset restores every identity.
Hidden elements and connections have no hit areas. No evidence or rule changes.
Filtering can make dense levels readable; it cannot certify a complete overview's
layout.

[Element-filter proof](../../../tests/test_uml_visual_acceptance.py).
