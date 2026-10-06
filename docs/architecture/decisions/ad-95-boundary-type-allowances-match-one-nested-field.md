# AD-95 A boundary type allowance names one nested field finding

A boundary allowance identifies one finding by facade function, signature position, field path and
exact collected annotation. It exempts neither the function nor the source. A match emits a FACT;
unmatched allowances do nothing. Other findings and UNKNOWN survive.

[AD-199](ad-199-nested-permissions-pin-the-complete-field.md) pins complete nested declarations;
[AD-123](ad-123-proven-mappings-are-broad-boundary-types.md) permits one exact top-level broad
finding. Bare mappings cannot gain root permission.
[AD-135](ad-135-exact-native-payloads-accept-opacity.md) permits explicitly declared object opacity
without proving closure. Ambiguous or multiple matching maps remain unallowed.

Adding an allowance widens; removing it narrows. Proof:
[test_boundary_type_allowances.py](../../../tests/test_boundary_type_allowances.py).
