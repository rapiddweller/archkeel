# AD-312 TypeScript stream exposes an incomplete SQLite symbol snapshot

**Status.** Accepted for the first producer/reader slice.

**Decision.** `archkeel stream build/page` writes and pages canonical TypeScript symbol records and their canonical evidence in a local, atomically replaced SQLite file. The result always reports `INCOMPLETE`; its contract identity is `NOT_EVALUATED`. It cannot enter check, report, or Studio as a complete observation. `ProcessCollector.run_control` returns bounded control bytes in `BoundedControlResult`. The existing `collect_response` API keeps its request-only signature and validated `CollectionResponse | CollectionError` result. Both use one process runner for deadlines, output limits, stderr draining and cleanup; the stream CLI validates the control summary and reads the published snapshot back before reporting success.

**Reason.** This creates a usable SQLite producer and bounded reader without first constructing the complete `SourceFacts` or `Observation`, while reusing the collector's symbol IDs, record builder, and evidence builder.

Page counts are stored with the snapshot at publication. Cursor pages use the `(section, sequence)` primary-key index instead of recounting the whole records table.

**Limit.** This is not complete streaming or a trusted architecture graph. Calls, references, import bindings, re-exports, cross-file proofs, and full source validation are absent. Syntax trees, definitions and global indexes, gaps, evidence, and selected file paths remain resident during build. No memory or scale improvement is claimed. Scope is the existing TypeScript scan scope intersected with the explicit `--source`; tests outside that scope are not scanned, but tests inside it are not specially excluded.

**Alternative.** Copying full `SourceFacts` or `Observation` into SQLite would preserve the materialization this work targets. Publishing partial data through the trusted report path would claim validations this slice does not perform.

**Tests.** `tests/test_typescript_collect.py::test_sqlite_symbol_stream_preserves_canonical_facts_and_aborts_without_publication` checks canonical symbol/evidence parity, bounded CLI readback, UNKNOWN first-row paging, selected-input scope, SQLite integrity, oversized evidence rejection, and atomic abort. `tests/test_collection_process.py` checks bounded control output and timeout, plus the target graph for the shared process boundary and the unchanged validated response API. These are not a complete cross-file, coverage, or test-exclusion proof.
