# AD-163 Nested UML retains declaration ownership

An explicit inside contract can declare UML entities, relationships and completeness.
Each UML declaration requires Contract 2.2. Its outer contract can remain 2.1.
Legacy contracts keep their encoding and meaning.

Core authenticates the whole declaration tree and compiles one root UML target.
Missing inputs, identity collisions or changed owner metadata cannot produce a partial PASS.
The canonical target references existing component, module and layout record IDs.
It copies no physical declaration contents. Core compares the combined target once.

`ComponentIntent.parent_id` identifies architectural containment.
`Entity.parent_id` still identifies lexical containment.
Labels remain separate from namespaces and IDs. Layout references identify their owning
component; empty and absent file inventories retain their different meanings.
The producers agree on explicit UML, component hierarchy and physical intent.
[AD-164](ad-164-dependency-permissions-keep-one-owner.md) migrates `requires` permissions
into the canonical graph projection. Their existing records and Core rules remain authoritative.
They are not mandatory calls.

The existing contract tree values and input error live in `ir.model`.
Their `ir.codec` exports remain compatible. This removes the compiler/codec import cycle
without a new abstraction or a relaxed architecture rule.

Target and Diff navigate nested components, classes/interfaces and operations through
the common renderer. Details shows only the selected level's physical intent.
Legacy-only Target and global API migration remain open.

Proof: `tests/test_target_graph.py` and `tests/test_uml_rendering.py`.
