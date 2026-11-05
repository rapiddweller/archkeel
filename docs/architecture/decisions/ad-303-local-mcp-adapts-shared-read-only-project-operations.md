# AD-303 Local MCP adapts existing read-only operations

**Status.** Accepted for issue #845, model only. Builds on AD-290, AD-292 and AD-304. Sources checked
2026-11-05.

**Decision.**
1. Use the separate FastMCP distribution, not the official SDK. FastMCP 4.1.6 is the latest stable
   release on 2026-11-05 and supports Python 3.10+. Pin an exact release when code uses it.
2. Start with a local stdio server and read-only tools. The client launches the process; stdin/stdout
   carry MCP messages, and logs go to stderr.
3. Root `COMP-MCP` is the canonical planned owner (`lifecycle: planned`, no packages), under the same
   `components[]` policy used after promotion. It owns protocol registration, tool mapping and stdio.
   It requires existing `check.report:run_report` and the typed CHECK/IR interfaces declared in the
   root contract. It does not own collection, snapshot decoding, graph derivation, evaluation or
   story calculations. It does not depend on CLI or Studio HTTP/server/Workspace APIs.
4. Existing CHECK operation: `run_report(root, config: ScanConfig, analyzer: Analyzer, ...)` returns
   `tuple[RunResult, bytes | None]`. Existing IR owns `RunResult`, `ArchitectureReport`,
   `report_graph:architecture_report` and the public `ir.story` module. These are current interfaces,
   not a new shared result port. A common typed operation/session port has not been proven.
5. `run_report` needs an injected Analyzer. The CLI currently composes it through
   `cli.observe:observer_for`; MCP cannot import CLI under this boundary. No shared composition
   factory or session owner is established, so executable MCP composition remains open.
6. A second process cannot share Studio's in-memory `Workspace` directly. Target invariant: one
   canonical root/scope per session, one immutable snapshot revision per operation, and no second
   scan when attached. Results name root, scope, revision and current/stale/unknown freshness.
   Missing or incomplete evidence remains UNKNOWN. Source and contract digests may contribute to
   identity; their derivation is open. Live sharing requires a typed session interface that reaches
   its owner across processes; none is proven.
7. A trusted owner binds session identity; an MCP caller cannot choose it. Session creation,
   discovery, transfer, authentication and IPC remain open. A revision race is stale or UNKNOWN,
   never a mixed result.
8. A standalone local first slice may operate without Studio attachment; it must state this limit.
   Embedded Claude uses `--strict-mcp-config`; Codex uses `--ignore-user-config`, so neither
   automatically sees an external stdio server. Local stdio does not send source to remote services
   itself, but clients may forward tool outputs to their providers; do not promise all data stays
   local. Write tools require explicit approval, scope and failure behavior in a separate decision.
9. The planned owner has no source package. Consequently `COMPONENT-NO-CYCLES`, `INTERFACE-BOUNDARY`,
   `MODULE-NO-CYCLES` and `REQUIRES-COMPLETE` remain UNKNOWN in ArchKeel's self-contract; other rule
   assessments must retain their measured status. Self-validation must report UNKNOWN, not PASS.

**Compatibility.** MCP names 2026-07-28 as current and documents older revisions. Claude Code and
Codex document local stdio servers, but this does not prove client compatibility with FastMCP 4.1.6.
Probe versions before claiming support. Claude Code's stdio shutdown window is under one second on
macOS, Linux and Windows.

**Rejected.** FastMCP in the HTTP server; MCP calls through Studio HTTP or CLI subprocesses; duplicate
checker/story logic; writable first-slice tools; compatibility claims without client probes.

**Limits.** Contract ownership and `requires` are target intent, not source evidence. The four rules
above stay UNKNOWN until MCP code exists and is scanned. The model establishes no shared live Studio
state, IPC/authentication, session lifecycle, race handling, runtime behavior or client support.

**Sources.** Checked 2026-11-05: [FastMCP 4.1.6](https://pypi.org/project/fastmcp/4.1.6/);
[installation](https://gofastmcp.com/getting-started/installation); [MCP versioning](https://modelcontextprotocol.io/specification/versioning)
and [stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports); [Claude Code](https://code.claude.com/docs/en/mcp)
and [Codex](https://developers.openai.com/codex/mcp).
