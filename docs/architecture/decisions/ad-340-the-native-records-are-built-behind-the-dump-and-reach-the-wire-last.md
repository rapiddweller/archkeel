# AD-340 The native records are built behind the dump and reach the wire last

**Decision.** PR 4.3a-3 of issue #880 (the records of the native TypeScript collector) is four PRs.
The records are built and compared with the unmodified Python collector first. The reply stays the
legacy reply of AD-320 (sections `imports` and `unknowns`, no construct capability) until the last
PR, so the host cannot read a new record and no verdict can change. This record extends AD-323.

1. **3a: the expanded imports and the constructs.** `records.rs` builds one `IMP_BINDING` record for
   each bound name (`_named_imports`), the `ESM_EXPORT` witnesses and the `TSCONSTRUCT` records
   (`_constructs`). The `dump` feature prints them with `--dump-records`.
2. **3b: symbols** (`TSDEF`). **3c: calls, references and bindings** with the resolver.
3. **3d: the streamed reply, the flip and the verdict differential.** Only 3d moves the records into
   `Facts.sections` and declares the inner-UML capability. `Facts.sections` holds any section by
   name and `Facts.constructs` the construct capabilities.

**Oracle.** `tests/test_collector_native_records.py` runs the Python methods in the order of
`_Collection.facts()` up to `_constructs()` and compares all sections and the cited evidence on the
fixtures, the Studio UI, the resolution grid, mutated projects and `ARCHKEEL_RECORDS_CORPORA`.

**Cost.** Python scans the bindings of a file for each statement and the exports of a module for
each bound name. `Kept` indexes both, so n statements and n exports stay linear. Four shapes have a time
ratio and a memory bound; they found a loop of PR 4.2 (`Snapshot::read`, now `readable`).

**Note, 2026-11-09 (3b): symbols.** `symbols.rs` builds one `TSDEF` record for each definition, and
`symbol_table.rs` is the table that 3c reads (`at`, `with_qualified`, `count`, `classifier_count`,
`scope`, `top_level`, `in_module`). Counts are constant time, so a name with k definitions costs k;
a map keyed by module, parent name and position replaces the scan of all definitions for each
class. The evidence of a location is decided by its last citation (`record_evidence` overwrites), so
`Cited` starts from the evidence of the reply and the new records cite in the order of Python:
imports, symbols, sites, constructs.

**Note, 2026-11-09 (3c): calls, references and bindings.** `site_records.rs` builds the `TSCALL`,
`TSREF` and `VALUEBIND` records and `resolution.rs` is the syntactic resolver. The symbol table
answers each lookup that Python does by a scan (`top_named`, `named_in`, `has_member`,
`class_count`), and `NameIndex` answers "does a scope of the chain hide this name" with one binary
search in the positions of the name. Not ported: the script paths (`script_resolution`,
`script_evidence`, `_script_alias_bindings`, PR 4.3a-4 and 4.3a-5). The oracle is the Python
collector **without `_script_dependencies`**, which Python runs on every file that is neither a
declaration nor CommonJS, an ES module included: `Scene.create()` in `mod.ts`, with `legacy.js`
publishing `Scene`, is `resolved` in full Python (fact `SCRIPTPUBLICATION`) and `unresolved` here;
a strict xfail test pins it. `NameIndex` keeps parameter ranges that grow with the depth of the
nest: 10 000 nested scopes with 100 000 sites take 2.2 s against 1.1 s (not fixed).

**Note, 2026-11-09 (3d): the flip.** The reply declares seven sections, `inner-uml-v1` and the construct
`string_literal_compare` as `partial`. The host reads it as the reply of the default collector, except
the closed list: script facts (the 4.2 gap stays, so every verdict that needs them is `UNKNOWN`),
provenance, and the script-global case of 3c. One producer, `Plan::write` in `records.rs`, gives
each section to a sink: `native/wire/src/stream.rs` writes the head, each record (dropped after it is
written) and the tail through the compressor to stdout, and fails when a declared section is not
written or an undeclared one is; the lists of the tests use the same code. Data keys have another
order than Python, so tests compare decoded values.

**Precondition for 4.3a-5.** The host takes a declared section that is present and empty as
complete: with the default collector `calls`, `references` and `constructs` emptied give
`complete=PASS` (`imports`, `symbols`, `bindings` give UNKNOWN). The native collector is safe only
while the 4.2 gap makes every scan incomplete. Before the gap goes, the host must refuse a claimed
and empty section (the strict xfail `test_a_section_that_is_emptied_is_never_a_pass`).

**Cost.** x35: collector 2.9 s and 431 MiB (3c: 1.0 s, 117 MiB), reply 36 MB; the host decodes the
whole reply (2.9 GiB). The gate of at most 2 times the time of 3c is missed (2.9 times): after the
walk, the time goes to building and writing 270 MB of JSON (malloc, copy), not to the compressor
(stored blocks take as long; zlib-rs is 2 % faster and its licence is not allowed). The quadratic
replies by the data model (the qualified name of each nested definition is in each record) are
timed by their time for each byte of the reply and by an absolute peak (192 MiB) on the real
collector, and by `--dump-count` for the walk. A shared name cut `writes-distinct-names` n=8 000
from 1 302 to 474 MiB.
