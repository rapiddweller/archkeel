# AD-74 A name bound twice is unresolvable, not a coin flip

Distinct bindings for the same module/name are ambiguous UNKNOWN. Repeated imports to one proven
origin remain one binding. Do not select a target by record hash or guess the runtime winner from
unordered facts.

Conditional definitions stay outside this proof; imports from different lexical scopes can
conservatively collide. Proof:
[test_boundary_type_ambiguous_bindings.py](../../../tests/test_boundary_type_ambiguous_bindings.py).
