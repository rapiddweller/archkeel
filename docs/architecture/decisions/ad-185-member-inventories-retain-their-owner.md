# AD-185 Member inventories retain their owner

A file scan does not prove a class member inventory complete. Python publishes
versioned `MemberInventory` receipts with definition-site identities in its class
records. The Python profile embeds the generated schema so existing consumers
need no new registry entry. IR owns the immutable type, generated schema and validation. Core owns
closed-scope comparison. Rendering consumes the existing graph coverage.

Each receipt names direct static attributes or methods. Conditional definitions,
unknown bases, rebinding and opaque class creation remain partial. Attributes
also remain partial when unannotated assignments or method effects are unmeasured.
Native dataclass methods remain partial because the collector does not enumerate
its generated operations. This makes no claim about runtime object shape.

The process codec and graph projector reject foreign, omitted or duplicate
member identities. Complete collection is still required. Legacy records inherit
the existing partial module coverage. No baseline or completeness rule is weakened.

Proof: `tests/test_member_inventory.py`: extra/missing fields, unsupported syntax,
legacy UNKNOWN, process roundtrip and malformed receipts.
