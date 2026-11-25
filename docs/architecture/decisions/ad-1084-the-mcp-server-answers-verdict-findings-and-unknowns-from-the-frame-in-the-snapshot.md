# AD-1084 The MCP server answers verdict, findings and unknowns from the frame in the snapshot

**Status.** Accepted (owner priority P1, 2026-11-25). Slice 1 of #1375. Closes #1984. It amends [AD-1038](ad-1038-explorer-surfaces-scip-call-resolution-separately.md): the snapshot has five more tables, and the format is 6.

**Reason.** An agent that builds ArchKeel must see violations and UNKNOWNs fast. The MCP server held structure only. The agent had to run `archkeel validate --json` and parse a frame of several MB.

**Decision.**
1. **Copy the core frame.** The snapshot publish step copies rows that the core already decided. It does not run the checker again. The tables are `verdict` (status, exit code, counts, contract digest), `rationale`, `violation`, `gap` and `source`. `source` holds the scan digest of each file that the scan assessed: the modules, the contract files and the config.
2. **One exit code.** `verdict.exit_code` is `exit_for(Outcome.VERDICT, frame, baseline=False)`. The MCP server maps no status to a code.
3. **Three read-only tools.** `verdict()`, `findings(rule, component, cursor, limit)` and `unknowns(kind, cursor, limit)`. `component` is a component id; a finding also belongs to each parent of its component.
4. **Basis.** A row has `basis`: `proven` (the core reported it), `declared` (the violation rests on a possible import that the contract declares) or `unknown`. A gap is always `unknown`. Nothing is `inferred`.
5. **Gaps.** `unknowns` lists the gaps of the frame and its collection gaps. A collection gap has a place (`at`). The kind is the kind of the core, for example `source_resolution_gap`. Its reason (`dynamic_import: eval`) is text of the core, and the tool does not parse it.
6. **Untrusted text.** The rule rationale and the gap reason come from the repository. They are objects `{"text", "untrusted": true}` cut at 300 characters. The tool descriptions are fixed text.
7. **Bounds.** Default `limit` 25, maximum 100. An answer has at most 16 KiB. A cut answer has `truncated: true`, the exact `total` and `next_cursor`. Rows are ordered by id, and the id follows the sort of the row. There is no timestamp, so equal input gives equal bytes.
8. **Freshness.** Each answer has `freshness`. It is `stale` when a file of `source` has another digest, is gone or cannot be read. It is never `fresh` on an error.
9. **No verdict.** An observed scan (no contract) and a snapshot of format 5 or older have no verdict. `verdict()` then gives `status: null` and `basis: unknown`. `findings` and `unknowns` refuse.

**Rejected.** A second MCP server. A second checker run. A freshness check by Git state (it needs the core binary and the shell layer). A `status` field that the server derives itself.

**Limit.** A file that is added after the scan does not make the answer stale. The documents that the contract cites are not in `source`. `accepted_by_baseline` is always false, because the snapshot scan reads no baseline file. Identifiers (rule ids, module names, paths) are not marked untrusted.

**Tests.** `tests/test_explorer_verdict.py` has one test for each acceptance item of #1984, a test of a scan without a verdict, of an older format and of `declared`. `tests/test_explorer_store.py` checks format 6 and the read of format 5.
