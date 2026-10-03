# AD-150 Source facts and Core evaluation have separate owners

Language adapters own parsing, resolution, local IR and source-fact collection.
`ir.facts`, `ir.source_records`, `ir.protocol` and their codecs define the shared
data boundary. They do not own architecture verdicts.

`check` validates source facts against the contract, applies one Core-owned rule
set and assembles the canonical observation. Governance models, rule availability,
metrics and verdicts stay outside every language adapter. `ir.profiles` owns the
capability and rule-availability table; `facts.Language` owns the language identity.

The process port makes collectors replaceable. It does not prove Python/Dart parity,
TypeScript package completion or runtime isolation. Each remains subject to its
own acceptance evidence.

The CLI-to-Core coupling ceiling moves from 11 to 14 names. The three additions are
`Observer`, `analyze_source_snapshot` and `ObservationResult`. They
compose the collector, preserve the snapshot entry point and type its result.
Exact names define this seam; whole-module grants would make its width unknown.

The self-baseline changes from the reviewed snapshot baseline: unresolved calls
597 to 674, typing positions 53 to 59, UNKNOWN positions 40 to 42. Independent tests
retain upstream snapshot and inheritance findings, including UNKNOWN cases.
The new code adds process and protocol boundaries; recursive JSON and compatibility
reexports still have explicit static limits. A redundant process-module publication
was removed before recording the new counts. Violations, cycles and private-use
debt remain zero. This baseline records the reviewed implementation; it does not
claim that UNKNOWN evidence is resolved.

Reports preserve producer metadata for every language, including Python. Code digests
come from the Core and collector source bytes, not the installed package version. The
optional producer field keeps older Python reports valid while new reports identify
the producer and its source digest.
