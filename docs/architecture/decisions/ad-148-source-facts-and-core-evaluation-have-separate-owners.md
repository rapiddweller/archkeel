# AD-148 Source facts and Core evaluation have separate owners

Language adapters own parsing, resolution, local IR and source-fact collection.
`ir.facts`, `ir.source_records`, `ir.protocol` and their codecs define the shared
data boundary. They do not own architecture verdicts.

`check` validates source facts against the contract, applies one Core-owned rule
set and assembles the canonical observation. Governance models, rule availability,
metrics and verdicts stay outside every language adapter. `ir.profiles` owns the
rule and metric availability; source facts declare per-construct support.
`facts.Language` owns the language identity.

Core verifies construct owners against observed modules and their cited files.
It checks every collector's `{name, version, required}` runtime and retains
UNKNOWN for partial construct support. Metadata-only versions do not alter
code identity. The process host cleans descendants after every exchange.

Delta 1.4 compares only the profile's measurable dimensions. Python keeps its full scope;
Dart and TypeScript leave API, private and typing dimensions UNKNOWN with null counts.
Coverage PASS requires every applicable dimension and complete, comparable snapshots.
Expectations cannot select an unavailable dimension or grant it support through a supplied delta.
Historical delta 1.3 remains readable; scoped comparison requires reobservation.

The process port makes collectors replaceable. It does not prove Python/Dart parity,
TypeScript package completion or runtime isolation. Each remains subject to its
own acceptance evidence.

The CLI-to-Core coupling ceiling moves from 10 to 14 names. The four additions are
`Observer`, `analyze_source_snapshot`, `Language` and `ObservationResult`. They
compose the collector, preserve the snapshot entry point and type its result.
Exact names define this seam; whole-module grants would make its width unknown.

The unchanged parent source measures 597 unresolved calls, 53 typing positions
and 40 UNKNOWN positions under Core. The migrated source measures 682, 53 and 42.
Process cleanup, provenance, protocol validation and typed fact extraction add
unresolved stdlib/receiver calls. New recursive JSON seams and compatibility
reexport routes remain UNKNOWN. Internal JSON helpers use validated `RawJson`;
the typing baseline stays unchanged. Violations, cycles and private-use debt stay
zero. These measured source-baseline changes require independent review; they
do not resolve UNKNOWN evidence or widen a contract budget.
