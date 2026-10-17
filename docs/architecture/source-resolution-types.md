# Source-resolution types

Source collectors own three claims: `resolved`, `partially_resolved` and
`unresolved`. `ir.facts.SourceResolution` owns that existing wire vocabulary.
It replaces the Dart collector's fact-status enum and the TypeScript collector's
duplicate vocabulary. Python call, reference, base and construction producers use
the same nominal values before serializing source facts.

`parse_source_resolution` recognizes the vocabulary where Core consumes a
resolution claim. It returns `None` for absent, malformed or future values without
rewriting their record data. The source protocol still validates strings and its
existing required fields. Base declarations retain their existing closed
validation; calls and references retain open status strings. Generic record kinds,
nested metadata and arbitrary record data remain open.

`CallStatus` is the named `Literal` subset containing only
`SourceResolution.UNRESOLVED` and `SourceResolution.PARTIALLY_RESOLVED`.
`CallRow` normalizes legacy construction inputs once and rejects a resolved or
unknown value. It continues to represent only calls without one proven target.

Graph `ResolutionKind.PARTIAL` uses the different wire spelling `partial`.
The source-to-graph port explicitly maps the shared source enum to that domain.
Dart resolver `ResolutionStatus.UNKNOWN` is also a separate claim and is not a
source-resolution value.

The focused tests exercise actual Python producers, strict source-protocol
round trips for future values, the narrow call-row boundary, the fixed native
SourceResolution/CallRow target and native raw-control/type-weakening mutations.
Verification also compares isolated collector and Core runtimes across Python,
Dart and TypeScript fixtures. Only analyzer code digests may differ in those
observation bytes.
