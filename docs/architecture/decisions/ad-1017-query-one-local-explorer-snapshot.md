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
