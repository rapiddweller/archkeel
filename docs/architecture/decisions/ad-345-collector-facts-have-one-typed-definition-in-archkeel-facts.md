# AD-345 Collector facts have one typed definition in archkeel-facts

**Decision.** The crate `native/facts` (`archkeel-facts`) holds the one typed definition of each
collector fact that crosses the process boundary. It is target v2 WP3a of epic #880. A collector
builds these types. The wire, the read-set and the JSON schema come from the same types.

**Problem.** `Record.area` and `Record.kind` were free strings, and `Record.data` was a
`Map<String, Value>` (`native/wire/src/reply.rs`). Rust and Python held two hand-written type sets.
A typo in a kind or a field reached the host as data.

1. **Closed vocabularies.** `Area`, `Kind` (53 kinds), `Status`, `ReasonCode` and the value sets of
   the WP1 inventory, also inside nested objects, are enums. A value outside a list is a decode
   error. The open gap kind of protocol 9 (an exception class name such as `SyntaxError`) is
   `Kind::ExceptionGap`. The name is a closed `ExceptionName` field, and the area must be
   `analysis_coverage`. The list holds the names that the Python and Dart collectors can write.
2. **Typed records.** `Record<D>` holds the shared fields. `D` is the data enum of one section, so
   a record cannot hold the data of another kind. The data types are the union of the fields of
   the TypeScript, Python, Dart and Rust collectors. Each nested object rejects an unknown key. A
   field that the wire always writes, also as `null`, must be present (`nullable::required`); a
   field that one producer omits and another writes as `null` is a `Nullable`.
3. **Ids.** `FactId`, `EvidenceId`, `ModuleName` and `PackageName` are newtypes with no conversion
   between them. The Target id type comes with the model crate.
4. **Producer identity.** `Producer` holds name, version, code digest and origin (bundled or
   external). Protocol 9 does not carry the origin; protocol 10 does.
5. **Two serializers.** `serde` writes the protocol 9 wire. For the native TypeScript collector it
   is byte-equal to the reply of today. A Python or Dart reply gives an equal value, not equal
   bytes: Python sorts the keys. `readset::ReadSet` writes the data fields that WP1 lists as read
   for the area and the kind (`readset_fields`); `[read]`/`[wire]` and `skip` are two marks.
   The exception name and `GapData::code` are in the read-set only.
6. **Schema.** `schema::schema()` generates a draft 2020-12 bundle with schemars, pinned to an
   exact version. `native/facts/schema/archkeel-facts-9.schema.json` must equal it. A published
   schema never changes; a type change that changes it needs a new protocol.
7. **First adopter.** The native TypeScript collector builds the `imports` section with these
   types (`wire::reply::ReplySection::Typed`). The other sections move one by one.
8. **Layers.** `archkeel-facts` is a library that uses no other crate and no parser. The wire and
   the collectors may use it (the contract of `native/`). The serde derives need `unicode-ident`
   (Unicode-3.0) in the compiler; `deny.toml` allows it for that crate only.

**Rejected.**
- **A hand-written schema.** It is a second definition that can drift from the code.
- **One open `Map` for the data.** It is the state that this record removes.
- **A read-set mode flag inside `serde`.** A thread-local switch hides the flow; a second trait
  shows it.
- **PyO3 views.** Closed by the owner on 2026-11-10: no gain over the JSON read-set (WP2).

**Limit.** The exception name list can miss a rare Python `OSError` subclass; it is a decode
error, not a wrong fact. A kind that no WP1 reply showed has no read list: the read-set writes
its `[read]` fields. The data types are inferred from the WP1 replies and the collector code. A field that
no reply showed and no code read is not in a type. The union types allow a producer to write a
field of another producer. `facts.state`, `type_shapes`, `provider_bindings`, `inputs`, `files`,
`imports` and `evidence` are not typed yet. The host Python does not read the read-set yet.

**Checked by** `native/facts/src/sections_tests.rs` (the widest and the narrowest record of each
kind of each producer decode and encode equal; the exception gap and its area; a gap kind outside
the lists; the read-set of each record equals the WP1 read-set), `record_tests.rs` (the wire of
an import byte for byte, the read-set fields, decode errors, a missing `null` field), `schema_tests.rs` (the committed
schema equals the generated one), `vocab_tests.rs`, and
`native/wire/src/reply_tests.rs::a_typed_import_section_writes_the_bytes_of_the_map_record`.
