# AD-68 `check` and `render` declare `boundary_types`, and the ten findings are declarations

Declare the types that check and render facades actually expose. These are provider-owned boundary
contracts, not debt to baseline. Signature exposure
([AD-65](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md)) makes the declarations used
even when consumers pass values without importing the names.

Use a typed mapping for files-to-write. Keep unresolved positions visible; declarations do not prove
closure. Proof: [test_self.py](../../../tests/test_self.py).
