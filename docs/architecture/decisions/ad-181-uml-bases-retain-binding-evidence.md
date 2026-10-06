# AD-181 UML bases retain binding evidence

Record explicit Python base expressions with kind, site and binding limits.
Proven Protocol implementation yields `realizes`; subprotocols yield `inherits`.
Matching signatures alone prove neither. Expressions are never executed.

Each classifier retains base-list coverage. Core uses the nearest covering receipt
without dropping descendant limits: a complete local list can prove a missing base,
an unresolved one cannot. Child receipts cannot certify unmeasured parents or siblings.
Adapters collect evidence; Core compares independent Target.

[Base proof](../../../tests/test_uml_classifier_facts.py).
