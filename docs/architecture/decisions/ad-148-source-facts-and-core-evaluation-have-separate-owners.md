# AD-148 Source facts and Core evaluation have separate owners

Language adapters own parsing, resolution and source facts. Shared IR defines
the data boundary; Core owns policy evaluation, metrics and verdicts. Core validates
construct owners, source evidence and collector runtimes. Partial support remains
UNKNOWN; metadata versions cannot substitute for code identity.

Compare only profile-measurable dimensions. Unavailable metrics remain null;
expectations cannot grant missing capability. Coverage PASS requires complete,
comparable snapshots and every applicable dimension. Historical deltas remain readable;
scoped comparison requires reobservation. Replaceable collectors prove neither
language parity nor runtime isolation.

Runtime metadata uses SourceFacts/ArchitectureIR 2.0.0; Delta 2.0.0 and command-result
6.0.0 carry it. Legacy packets remain readable; collectors, Core and strict schemas
must be pinned together.

[Protocol proof](../../../tests/test_collection_protocol.py) and
[comparison proof](../../../tests/test_profile_comparison.py).
