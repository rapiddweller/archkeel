# AD-163 Nested UML retains declaration ownership

Compile explicit nested UML into one authenticated root Target and compare it
once in Core. A child UML declaration requires Contract 2.2; its outer contract
may remain 2.1. Legacy encoding stays compatible.

Authenticate the whole tree. Missing inputs, collisions or changed owners cannot
yield partial PASS. Architectural component containment stays separate from lexical
entity containment. References retain declaration ownership without copying physical
intent. Permissions remain allowed imports, not mandatory calls.

[Nested Target proof](../../../tests/test_target_graph.py).
