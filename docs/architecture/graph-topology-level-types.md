# Core graph topology levels

Part of #542. Core derives dependency edges, SCC records and transitive paths at module or package level. This domain is distinct from contract CycleLevel (component/module) and StructureLevel (component/package).

The existing ir.model owner provides GraphTopologyLevel and an optional JSON reader. Producers carry canonical levels through aggregate_edges and _cycle_records; callers use the enum. The reader recognizes known levels in open record data without mutating or rejecting unknown/future metadata. Record kinds and observation section names remain open.

The two producer functions are internal to TARGET-EVALUATION, with only two actual callers each and no public raw-string ingress. No legacy normalizer or new record DTO is introduced.

Normative Targets cover the enum, reader return and exact producer parameters. Required tests exercise real wire producers, opaque metadata, actual signature/kind weakening and two exact function control mutations. Root owns final union review, combined metadata and Main gates.

Design/owner handoff approved by Root on frozen bb3e498b9c43afc954ef9fe7078595983e0b3c2f. Actual producer/caller AST inventory: run39000792772/job117303082614.
