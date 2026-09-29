# AD-123 Proven mappings are broad boundary types

`boundary_types` already rejects `dict[K, V]`: naming an open record's key and
value types does not make its fields a declared model (AD-58). The same rule now
applies to `Mapping[K, V]` and `MutableMapping[K, V]` when their standard-library
binding is proven. Renaming `dict` must not turn a violation into PASS. A bare `Mapping` or
`MutableMapping` with the same proof is the same finding, in a parameter, a return, an
`Optional`/`| None` member or a collection element: dropping the parameters does not declare a
record shape either.

The shared annotation reader still resolves both member types. An undeclared
member remains a separate violation; an undecidable member remains UNKNOWN.
Malformed arity, shadowed mapping names (a shadowed `dict` still reports a violation), and
imports the analyzer cannot prove remain UNKNOWN. A known violation and an undecidable member
can coexist; an exact allowance removes only the violation, never the UNKNOWN.
`allowed_positions` uses an empty `field_path` for a direct signature position and a named
path for a nested field. The direct selector matches the complete outer annotation;
neither selector exempts sibling or member-type findings.
Container depth is retained in each finding, so identical type text at the
root and inside a map or collection cannot make one allowance remove both.

Archkeel itself keeps three reviewed open maps: `FilesToWrite` accepts arbitrary
paths and `run_check`/`Host` accept arbitrary environment names. Its own contract
names each signature position exactly. The self-baseline drops from 48 to 40
UNKNOWN positions; it gains no violation budget. A root allowance cannot name a bare `Dict`,
`object`, `Mapping` or `MutableMapping` (AD-95).

This changes analyzer results, so `ANALYZER_VERSION` rises to `0.59.0`. The
DATAMIMIC CE demographic override exposed the gap: its public type correctly
permits a weighted map, but the old analyzer reported only `generic` UNKNOWN.

Upgrading: the new analyzer can report more violations under an existing baseline fingerprint
(`dict[str, UndeclaredModel]` now counts the map and the member). Review existing baselines and
re-accept them with `--write-baseline --accept-new`.
