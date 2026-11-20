# AD-1017 Studio and MCP query one local snapshot

**Decision.** The local Explorer publishes derived SQLite snapshots as specified by AD-310.
The browser and the optional stdio MCP adapter use the same read operations. The caller
selects an immutable snapshot at startup. Report topology retains its native verdict
and coverage. A source reference binds a repository path and content digest.
The database stores locations. The checked-out file supplies the text.

**Reason.** A repository can change while an architect or agent follows an import.
Binding each response to a snapshot keeps elements, evidence and source consistent.
A global cache limit bounds retained generations.

**Alternatives.** A separate graph service adds deployment and another store.
Saving full reports and source files in SQLite duplicates content on each scan.

**Limit.** Collectors can still materialize facts in memory. Incomplete coverage remains
visible. A process start or matching URL alone cannot establish the remote endpoint.

**Checks.** Explorer storage tests cover reuse, interrupted publication and bounded
storage. Query tests check paging, evidence and changed source. The corpus harness
exercises real repositories and reports its coverage.

The query component owns `explorer_symbols.py`. It groups methods and properties by
collector definition IDs. Member coverage comes from each class inventory.

`cli/core_explorer.py` serves the whiteboard. `explorer_store.py` publishes snapshots.
`explorer_queries.py` reads them. `explorer_mcp.py` exposes these reads over stdio.
`explorer_boundaries.py` records source hints for cross-language navigation.

With no Archkeel configuration, Studio uses the existing layout discovery in a private
copy of the Git working tree. Generated scanner inputs stay in that copy. The board
shows measured languages and counts. The inspector lists resolved external imports.
The report serves its gap evidence on demand. It retains up to 64 MiB of rendered
report and gap data in memory and renders larger reports again when requested.

Studio chat uses the signed-in Codex CLI to propose a view spec from bounded snapshot
facts. The storyboard checks each step before display (AD-291). The browser and MCP
use the same story store. An explicit save creates a new file in `.archkeel/stories/`.
A saved story can be shared. Saving one does not invalidate its source snapshot.
An optional `.archkeel/templates/story.md` supplies narrative guidance.

Studio uses the report's pinned ELK engine, box placement and relationship routing.
Map groups follow source directories, component ownership and declared layers.
A call between two modules links to an observed symbol call. A call with no resolved
target contributes to the source count and has no destination on the map.
