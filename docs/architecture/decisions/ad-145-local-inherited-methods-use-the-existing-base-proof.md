# AD-145 Local inherited methods use the existing base proof

Check effective methods through one proven local base/alias chain using existing
TypeVar substitution. Resolve signatures in their defining scopes; subclass bindings
shadow inherited members, annotation-only names do not. Constructors, overloads,
properties and supported abstract methods share direct-method policy.

Missing ancestors, multiple-base order, mutation, exposed native owners and unproved
creation or decorators retain UNKNOWN. A complete surface removes only its synthetic
placeholder; missing annotations still remain UNKNOWN. Preserve raw annotations,
stable IDs and both declaration sites. Identity and member-closure proofs stay separate;
no Python execution or full MRO inference.

[Inheritance proof](../../../tests/test_local_inherited_methods.py) and
[property proof](../../../tests/test_inherited_properties.py).
