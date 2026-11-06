# AD-312 Private SQLite staging for versioned fact batches

**Status.** Accepted implementation slice. It does not replace collection or validation.

**Decision.** Define a language-neutral, versioned `FactBatch` over canonical `Record` and
`Evidence` values. The shared codec reuses the existing strict parsers. A private SQLite store
accepts byte-limited frames, enforces a cumulative encoded-frame budget per snapshot, rejects
duplicate IDs and missing evidence references, and exposes bounded one-frame reads. SQLite's
`max_page_count` caps the main database file; the store also checks database and sidecar sizes
after each batch and aborts when that check exceeds the configured database limit. This
post-write check is not a hard cap on transient journal/VFS growth. Journal/VFS peak size is
unmeasured and remains `UNKNOWN`. The default frame and database limits are each 256 MiB. A
committed snapshot is always `INCOMPLETE`. Abort rolls back the new snapshot and preserves earlier
snapshots.

**Trust boundary.** The store does not run architecture rules or publish data to checks, reports,
or Studio. The existing full `SourceFacts` validation remains authoritative. No batch snapshot can
claim complete coverage until that validation consumes the staged data.

**Reason.** A shared batch and staging contract gives Python and a future Rust producer the same
transport and storage path. SQLite remains a derived local artifact. The first slice can test frame
bounds and atomic storage without duplicating language-specific policy.

**Rejected.** Add a Rust SQLite writer: this duplicates storage and trust policy. Expose a new CLI
or Studio reader: neither has a validated complete snapshot to serve yet. Copy a full
`SourceFacts` into SQLite: this does not remove full materialization.

**Limit.** The current collector still builds complete `SourceFacts`; the parent still assembles a
complete `Observation`. Cross-file semantic validation, coverage validation, process framing,
collector integration, and trusted publication are not implemented here. The store only checks
frame structure, ID uniqueness, and record-to-evidence references. The database budget is a local
resource ceiling, not a measured memory or throughput target.

**Tests.** Public small records cover canonical roundtrip, `UNKNOWN` preservation, per-frame and
per-snapshot frame limits, SQLite page limits, ID/reference rejection, `INCOMPLETE` status, and
abort rollback. No private source fixture or performance claim is included.
