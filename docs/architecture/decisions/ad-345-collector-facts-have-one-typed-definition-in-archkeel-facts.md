# AD-345 Collector facts have one typed definition in archkeel-facts

**Decision.** The crate `native/facts` (`archkeel-facts`) holds the one typed definition of each
collector fact that crosses the process boundary. It is target v2 WP3a of epic #880. A collector
builds these types. The wire, the read-set and the JSON schema come from the same types.

**Problem.** `Record.area` and `Record.kind` were free strings, and `Record.data` was a
`Map<String, Value>` (`native/wire/src/reply.rs`). Rust and Python held two hand-written type sets.
A typo in a kind or a field reached the host as data.

1. **Closed vocabularies.** `Area`, `Kind` (53 kinds), `Status`, `ReasonCode` and the value sets of
   the WP1 inventory are enums. A value outside the list is a decode error. The open Python gap
   kind (the exception class name, `SyntaxError`) is `Kind::ExceptionGap` with the name as a field.
2. **Typed records.** `Record<D>` holds the shared fields. `D` is the data enum of one section, so
   a record cannot hold the data of another kind. The data types are the union of the fields of
   the TypeScript, Python, Dart and Rust collectors. Each nested object rejects an unknown key.
3. **Ids.** `FactId`, `EvidenceId`, `ModuleName`, `PackageName` and `TargetId` are newtypes with
   no conversion between them. A source id never becomes a Target id.
4. **Producer identity.** `Producer` holds name, version, code digest and origin (bundled or
   external). Protocol 9 does not carry the origin; protocol 10 does.
5. **Two serializers.** `serde` writes the protocol 9 wire. It is byte-equal to the reply of
   today, so a collector adopts the types without a wire change. `readset::ReadSet` writes only
   the fields that a rule or a view reads (WP1). `GapData::code` is in the read-set only.
6. **Schema.** `schema::schema()` generates a draft 2020-12 bundle with schemars, pinned to an
   exact version. `native/facts/schema/archkeel-facts-9.schema.json` must equal it. A published
   schema never changes; a type change that changes it needs a new protocol.
7. **First adopter.** The native TypeScript collector builds the `imports` section with these
   types (`wire::reply::ReplySection::Typed`). The other sections move one by one.
8. **Layers.** `archkeel-facts` is a library that uses no other crate and no parser. The wire and
   the collectors may use it (`native/layers.toml`). The serde derives need `unicode-ident`
   (Unicode-3.0) in the compiler; `deny.toml` allows it for that crate only.

**Rejected.**
- **A hand-written schema.** It is a second definition that can drift from the code.
- **One open `Map` for the data.** It is the state that this record removes.
- **A read-set mode flag inside `serde`.** A thread-local switch hides the flow; a second trait
  shows it.
- **PyO3 views.** Closed by the owner on 2026-11-10: no gain over the JSON read-set (WP2).

**Limit.** The data types are inferred from the WP1 replies and the collector code. A field that
no reply showed and no code read is not in a type. The union types allow a producer to write a
field of another producer. `facts.state`, `type_shapes`, `provider_bindings`, `inputs`, `files`,
`imports` and `evidence` are not typed yet. The host Python does not read the read-set yet.

**Checked by** `native/facts/src/sections_tests.rs` (the widest and the narrowest record of each
kind of each producer decode and encode equal; the exception gap), `record_tests.rs` (the wire of
an import byte for byte, the read-set fields, decode errors), `schema_tests.rs` (the committed
schema equals the generated one), `vocab_tests.rs`, and
`native/wire/src/reply_tests.rs::a_typed_import_section_writes_the_bytes_of_the_map_record`.
