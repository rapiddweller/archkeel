# AD-1038 Explorer surfaces SCIP call resolution separately

**Decision.** Add a read-only `call_resolution` Explorer query operation served
identically over HTTP (`/api/v1/call_resolution`) and MCP (`call_resolution`),
and display its summary and paginated rows in the Studio inspector under an
explicit `"SCIP call evidence (separate from native AST)"` section.

**Reason.** AD-1036 stored verified SCIP call evidence in SQLite (`scip_artifact`,
`call_resolution`, and `call_resolution_count`) while keeping native calls,
architecture rules, and Stories separate. Without a read-only query operation,
Studio users and MCP agents could not inspect those classifications.

**Separation guarantee.** Existing operations (`overview`, `map`, `children`,
`search`, `relations`, `evidence`, `source`, `story`) keep their exact native
responses with or without SCIP tables. The `call_resolution` operation returns
`available: false` when a snapshot has no SCIP tables, and supports bounded
cursor pagination (`limit` up to 200) and optional filtering by `element`,
`status`, `provenance`, and `call_id`.

**Limits.** This projection is read-only. It never promotes SCIP bindings into
native AST edges, Stories, or contract verdicts, and it currently reads Rust
SCIP rows while remaining compatible with multi-language `scip_artifact` schemas.
