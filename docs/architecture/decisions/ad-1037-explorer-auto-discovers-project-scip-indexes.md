# AD-1037 Explorer auto-discovers project SCIP indexes

**Decision.** When `archkeel explore` starts without `--scip` or `--no-scip`,
it checks `.archkeel/scip/rust.scip` inside the project root without crossing
symlinks. If that regular file exists and verifies against the scanned source,
Explorer binds it to the snapshot and stores its call evidence in SQLite. If an
auto-discovered index is stale, malformed, or does not apply to the scanned
languages, Explorer writes one notice to stderr and opens the plain native
snapshot. Explicit `--scip PATH` keeps fail-closed refusal. `--no-scip` disables
auto-discovery.

**Reason.** Phase 0 measurements showed less than 1 MiB process-tree overhead
for verified SCIP ingestion on ArchKeel. Auto-discovery lets teams commit or
generate `.archkeel/scip/rust.scip` in CI and get call evidence by default
without blocking local Explorer runs while source edits are in progress.

**Source fingerprint and schema.** The Explorer source fingerprint excludes
`.archkeel/scip/*`, matching `.archkeel/stories/*.story.json`, so refreshing a
local SCIP file never perturbs the native source digest. `scip_artifact` adds a
`language` column with primary key `(language, index_sha256)` and bumps the
cache identity tag to `scip-evidence-3`, preparing the schema for Python,
TypeScript, and Dart SCIP indexes without another breaking table change.

**Limits.** Auto-discovery currently looks only for `.archkeel/scip/rust.scip`.
The producer still runs outside ArchKeel. Native calls, architecture rules, and
Stories keep their existing data from AD-1036.
