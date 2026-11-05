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
4. Keep one owner for each operation. Reuse the check, IR, workspace, graph and story services
   through typed interfaces. Do not call another adapter or duplicate checks. The existing
   Studio `Workspace` is the candidate session owner; test it before changing its ownership.
5. Bind one explicit project root and source scope for a server process. Every result names the
   project and snapshot identity. The shared workspace owns one current snapshot and revision.
   Use source and contract digests to identify it. Report freshness as current, stale, or unknown.
   Missing or incomplete evidence stays UNKNOWN.
6. Keep CLI output, Studio HTTP JSON, and MCP results as separate wire contracts. Their adapters
   map the same typed operation results. No adapter imports another adapter's wire types.
7. Add write tools only after a separate decision defines the user approval step, scope, and
   failure behavior. MCP tool annotations alone are not approval.
8. The target has one session for one canonical root and source scope. Studio creates the opaque
   session identity; the MCP client must not choose or forge it. MCP attaches to that session and
   never starts a second scan. The session returns one immutable snapshot revision per operation.
   Results name the revision. If it advances during a call, return stale or retry; never mix
   revisions.
9. The MCP process must reach the session owner across a process boundary. A stdio server is a
   separate client-launched process, and Studio keeps its workspace and snapshot in memory. A
   shared typed session interface is required. `run_stdio(root, sources)` does not accept a
   caller-supplied session ID: there is no proven secure handoff from Studio to this separate
   process, and a user-provided ID would not establish authorization. Session discovery, local
   transport, access control, shutdown and cross-platform behavior remain open until a prototype
   proves them. Do not route MCP through Studio HTTP or a CLI subprocess.
10. A first read-only slice can use a standalone session if it cannot attach to Studio. It must
    report that limit and must not claim live sharing. An opaque session ID is an internal
    binding identity, not a public run option; no authentication mechanism is selected yet.
    External MCP clients also differ from
    Studio chat: embedded Claude uses strict MCP configuration, and Codex ignores user
    configuration. Neither sees this server by default.
11. The current self-contract marks only planned `Workspace` session ports. It cannot represent a
    planned MCP owner: components need a package or exact module, and UML Target rejects owners.
    Add the owner and adapter symbols once its package exists, before adapter behavior; then add
    transport and lifecycle checks. The current model does not enforce an absent adapter.

**Compatibility.** The MCP specification names 2026-07-28 as current and documents older-revision
compatibility. Claude Code and Codex document local stdio servers. These facts do not prove that
FastMCP 4.1.6 works with a particular client release. Probe both clients before claiming support
and record their versions. Claude Code allows less than one second for stdio shutdown on macOS,
Linux, and Windows; the adapter must not rely on a long cleanup window.

**Rejected.** FastMCP inside the HTTP server; MCP calls to Studio HTTP; duplicated command or
checker logic; writable tools in the first slice; a compatibility promise without client probes.

**Limits.** `Workspace` owns a private in-memory snapshot and graph under locks. A second process
cannot reuse those objects directly. No session interface or MCP adapter exists. The current
contract can track planned Workspace ports; it cannot model an owner without a package/module or
prove IPC, race handling, runtime behavior, or client support.

**Sources checked 2026-11-05.** [FastMCP 4.1.6 on PyPI](https://pypi.org/project/fastmcp/4.1.6/);
[FastMCP install and pin guidance](https://gofastmcp.com/getting-started/installation);
[MCP versioning](https://modelcontextprotocol.io/specification/versioning) and
[stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports);
[Claude Code MCP](https://code.claude.com/docs/en/mcp) and
[Codex MCP](https://developers.openai.com/codex/mcp).

**Checks.** `tests/test_studio_mcp_target.py`; prototype the session boundary before adapter conformance tests.
