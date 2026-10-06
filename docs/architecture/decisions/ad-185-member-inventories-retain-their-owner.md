# AD-185 Member inventories retain their owner

Publish member-inventory receipts bound to exact class definition sites.
File coverage alone cannot prove complete methods or attributes. IR validates
receipts; Core owns closed-scope comparison.

Conditional members, uncertain bases, rebinding, opaque creation and unmeasured
assignment/effects remain partial. Generated dataclass methods are unenumerated;
runtime shape is unproved. Reject foreign, missing and duplicate member identities.
Legacy records retain partial module coverage; no completeness rule or baseline
is weakened.

[Inventory proof](../../../tests/test_member_inventory.py).
