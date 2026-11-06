# AD-310 SQLite stores derived streaming snapshots

**Status.** User-selected target direction. No implementation or performance result is claimed.

**Decision.** Keep versioned Git contracts as the source of architecture policy. Use local SQLite snapshots as derived, rebuildable analysis data. The collector streams facts into snapshots. Studio serves bounded, indexed queries from them. Preserve existing public CLI and API formats until a compatible migration is defined.

The current collector builds all `SourceFacts` before it returns. The parent process then builds the full `Observation`. This path does not stream facts into storage. A change must remove both full in-memory builds from the streaming path.

The snapshot format has an explicit version and records the source revision and contract identity used to build it. Readers reject unsupported versions or mismatched identities. They do not combine facts from different source or contract states.

Publish each completed scan atomically, including its coverage state. A complete snapshot can report INCOMPLETE, FAIL, and UNKNOWN. Build privately and mark transaction completion before publication. After a crash or aborted transaction, never report the snapshot as finished. Never present an older snapshot as current for a newer source revision. Checkpoint and close the WAL before publication so the snapshot is self-contained.

Collection, validation, storage, or query failures remain errors or UNKNOWN. Missing facts do not become negative findings. Tests cover partial input, interruption, version and identity mismatch, atomic replacement, WAL recovery, bounded indexed queries, and compatibility with supported older data.

Do not require SQLite files or WAL side files in Git. Do not claim a memory, latency, or scale target as achieved without a measured result.

**Rejected.** Keep full `SourceFacts` and `Observation` in memory: this preserves the current unbounded materialization path. Store derived snapshots in Git: this couples local cache state to source history and risks committing generated data. Add a separate service or database: local SQLite provides the required query index without another owner.

**Limit.** This decision selects storage and data-flow direction. It does not define a schema, query API, eviction policy, or performance target. Tests and measurements must set and verify those details during implementation.

**Basis.** The user selected this direction to address measured problems and the need for bounded Studio queries. AD-307 keeps Git contracts authoritative and rejects a database without a concrete need. The selection claims no performance result.
