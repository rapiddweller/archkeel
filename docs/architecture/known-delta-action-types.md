# Known Delta action boundaries

Part of #542. The existing SemanticChange model owns exactly four actions understood by current Core production and governance. The public SemanticChange.change field remains open str: future vendor actions roundtrip unchanged through every supported Delta version and are rejected only when current governance must interpret an unsupported action.

KnownSemanticChangeKind is shared by the actual Delta classifier and ExpectedSemanticChange. Governance converts input once, then keeps nominal identity keys through count, cycle, selected-change and guardrail decisions. The existing UnresolvedCallChange added/removed domain is narrower and unchanged.

The authored API Target pins the enum, open wire field and actual producer/selected-action/decoder/count ports. Native guards cover actual source projections of those migrated ports. Mixed full modules still contain pending dimension/schema/cycle vocabularies; this increment does not claim whole-module absence of raw string decisions. No new production module, generic conversion framework or schema is introduced.

Verification and exact Source/site evidence will be recorded after hosted RED/GREEN.
