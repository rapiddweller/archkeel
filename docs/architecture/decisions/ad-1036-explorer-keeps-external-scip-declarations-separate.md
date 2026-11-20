# AD-1036 Explorer keeps external SCIP resolution data separate

**Decision.** The optional `--scip` path consumes a finished index in the
Rust collector worker. The worker reads one document at a time. It joins
exact written callee spans to indexed references and existing declaration
identities. The shell streams the typed rows into the Explorer SQLite
transaction. Native calls, architecture rules, Stories and the browser
and MCP query projection use their existing data.

**Reason.** SCIP records symbol occurrences and declaration identities.
That is useful resolution evidence at a written call token. It leaves
runtime dispatch, missing references and other architecture statements open.

**Source identity.** An embedded document must equal the scanned source.
A textless document needs a versioned detached manifest binding the index
digest and source-file hashes. The manifest expresses the producer's or
operator's claim about those bytes. The importer checks the claim against
the scan. It does not attest the producer. The cache key incorporates the
scan fingerprint, index hash and optional manifest hash. New or stale
inputs must pass verification before a snapshot is published.

**Limits.** This adapter handles Rust and UTF-8 byte ranges in legacy or
typed SCIP occurrence encoding. It accepts SCIP symbol identities without
invoking the producer or a project build. Macros keep their native syntax
classification. Trait dispatch requires an existing declaration ID.
An external symbol stays an external reference, including when its index
has no crate version.

**Ownership.** The worker adapter belongs to `rs-entry`. Its syntax
adapter uses syn and proc-macro2, its JSON protocol uses serde, and its
streaming digest uses sha2. The lead approved eleven additional first-slice
self-scan gaps, covering seven possible trait calls and four possible
destructors. The typed bindings add eight approved gaps, seven possible
trait calls and one destructor. Rule states and violations stayed unchanged.

## Snapshot rows

`explore --scip PATH` records evidence in three SQLite tables. The optional
sidecar is `PATH.manifest.json`. Textless index documents require a matching
sidecar digest. The CLI binds the artifact and source fingerprints to its
snapshot key.

| `call_resolution.status` | `provenance` | Payload |
| --- | --- | --- |
| `local_resolved` | `ast_exact` or `scip_verified` | Existing canonical definition ID and `direct` or `trait_dispatch` |
| `external_std`, `external_dep` | `scip_verified` | Crate name, optional version, exact symbol descriptor |
| `unresolved` | `ast_exact` | `macro_call` |
| `unresolved` | `scip_verified` | `unmapped_scip_ref` |
| `unresolved` | SQL NULL | `no_scip_ref` |

Each row uses the native call ID and names the language. The native call
relation uses `relation:call:<call_id>`. Verified reference ranges use zero-based,
half-open UTF-8 columns. When available, the existing declaration evidence ID
and its one-based source line accompany the canonical definition link.
`call_resolution_count` groups rows by language, status, provenance and reason.
`scip_artifact` records the index digest and optional manifest digest.
Browser and MCP queries continue to read the native projection.
