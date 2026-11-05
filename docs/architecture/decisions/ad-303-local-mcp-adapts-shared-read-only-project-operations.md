# AD-303 Local MCP adapts shared read-only project operations

**Status.** Accepted for issue #845, model only. Builds on AD-290 and AD-292. Checked sources on
2026-11-05.

**Decision.**
1. Use the separate FastMCP distribution. FastMCP 4.1.6 is the latest stable release on
   2026-11-05; its PyPI metadata supports Python 3.10 and later. Pin an exact release when code
   uses it. FastMCP can change behavior in minor releases; see the linked install guidance.
2. Start with a local stdio server and read-only tools. The client starts the process. The server
   reads MCP messages on stdin and writes only MCP messages on stdout. Log on stderr.
3. Keep the MCP adapter in its own component. It owns FastMCP registration, MCP input and output,
   and the stdio lifecycle. It does not own CLI parsing, HTTP routes, project discovery, snapshot
   decoding, graph derivation, story checks, or source analysis.
4. Keep one owner for each operation. Reuse check, IR, graph and story services through typed
   interfaces. Do not call another adapter or duplicate checks. `Workspace` owns one Studio
   explore child, snapshot and graph in-process; it has no session handle, attach API or revision
   (`src/archkeel/studio/workspace.py`). It is only a candidate for shared state ownership.
5. Target outputs identify the project root, source scope and snapshot revision. Source and
   contract digests are candidate identity inputs; the owner and calculation remain undecided.
   Report freshness as current, stale or unknown. Missing or incomplete evidence stays UNKNOWN.
6. Keep CLI output, Studio HTTP JSON, and MCP results as separate wire contracts. Their adapters
   map the same typed operation results. No adapter imports another adapter's wire types.
7. Add write tools only after a separate decision defines the user approval step, scope, and
   failure behavior. MCP tool annotations alone are not approval.
8. Target invariants: one canonical root and source scope map to one shared session; MCP does not
   start a second scan when attached. Each operation reads one immutable snapshot revision and
   names it in the result. If the revision changes during a call, return stale or retry; never mix
   revisions. Missing evidence stays UNKNOWN.
9. The MCP process must reach the session owner across a process boundary. A stdio server is a
   separate client-launched process, and Studio keeps its workspace and snapshot in memory. A
   shared typed session interface is required. Session identity must be bound by a trusted owner,
   not selected by an MCP caller. Who creates, discovers, transfers and authenticates it is open.
   No session ID argument, attach endpoint or IPC mechanism is established. Do not route MCP
   through Studio HTTP or a CLI subprocess.
10. A first read-only slice can use a standalone session if it cannot attach to Studio. It must
    report that limit and must not claim live sharing. No authentication mechanism is selected.
    External MCP clients also differ from
    Studio chat: embedded Claude uses strict MCP configuration, and Codex ignores user
    configuration. Neither sees this server by default.
11. The self-contract records the existing HTTP API/server ownership and their MCP exclusions; it
    cannot represent an MCP owner without a package or exact module, and UML Target rejects owner
    entities. #846 should add a target-only owner declaration. Until then, no MCP implementation
    boundary is enforced. Add that owner before adapter behavior, once its package exists.

**Compatibility.** The MCP specification names 2026-07-28 as current and documents older-revision
compatibility. Claude Code and Codex document local stdio servers. These facts do not prove that
FastMCP 4.1.6 works with a particular client release. Probe both clients before claiming support
and record their versions. Claude Code allows less than one second for stdio shutdown on macOS,
Linux, and Windows; the adapter must not rely on a long cleanup window.

**Rejected.** FastMCP inside the HTTP server; MCP calls to Studio HTTP; duplicated command or
checker logic; writable tools in the first slice; a compatibility promise without client probes.

**Limits.** A second process cannot reuse `Workspace` objects directly. No session interface or
MCP adapter exists. Target invariants above do not prove session ownership, IPC, race handling,
runtime behavior or client support. The self-contract cannot yet model the absent MCP owner.

**Sources checked 2026-11-05.** [FastMCP 4.1.6 on PyPI](https://pypi.org/project/fastmcp/4.1.6/);
[FastMCP install and pin guidance](https://gofastmcp.com/getting-started/installation);
[MCP versioning](https://modelcontextprotocol.io/specification/versioning) and
[stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports);
[Claude Code MCP](https://code.claude.com/docs/en/mcp) and
[Codex MCP](https://developers.openai.com/codex/mcp).

**Validation.** `make self-validate` checks the declared Studio boundary. Prototype the session
boundary before adding adapter or lifecycle conformance tests.
