# AD-1036 Explorer keeps external SCIP declarations separate

**Decision.** The optional `--scip` prototype runs in the Rust collector
worker. It streams one document at a time and joins a written Rust call
token to one indexed symbol and one native declaration. Explorer publishes
the external declaration as evidence on an existing unresolved call.

**Reason.** SCIP describes symbol occurrences. A declaration occurrence
can help explain an open call. The occurrence cannot establish native
resolution, runtime dispatch, or compliance with an architecture rule.

**Source identity.** The caller supplies a versioned sidecar binding the
index hash to hashes of the indexed source files. The worker validates
the bytes and exact positions. The sidecar is an external assertion from
the index producer or operator. Matching hashes establish identity and
freshness, while attestation of the producer remains outside the prototype.
Explorer ties the result to the existing source fingerprint and both
artifact hashes. On a warm start it checks those inputs again. Stale or
replaced inputs get a new key and must pass verification before publication.

**Limits.** This adapter accepts Rust, UTF-8 byte positions and the legacy
SCIP occurrence encoding used by the tested rust-analyzer. It requires a
unique written call and a unique native declaration ID. It skips macros,
constructors, trait dispatch and external targets. It never runs an index
producer or builds the scanned project. The caps apply to the input and
scan, including the number of documents and occurrences.

**Ownership.** The adapter lives with the Rust worker entry point.
Only its parser uses syn and proc-macro2. Its typed input uses serde, and
its streaming digest uses sha2. The lead approved eleven additional
self-scan gaps, covering seven possible trait calls and four possible
destructors. Rule states and violations are unchanged.
