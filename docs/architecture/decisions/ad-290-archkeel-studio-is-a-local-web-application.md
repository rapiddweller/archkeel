# AD-290 ArchKeel Studio is a local web application

**Status.** Accepted. Owner decisions of 2026-11-03, epic #783. Amends the "server" part of the
rejected lines of AD-284 and AD-285. The Explorer stays the only architecture renderer.

**Decision.**
1. `archkeel studio [--root PATH] [--no-open] [--stop] [--idle-exit MINUTES]` with the scope
   options of explore (`--language`, `--source`, `--namespace`, `--tsconfig`) serves a local app;
   the CLI opens the browser. Studio is parallel to the static report, the CI and Pages artifact.
2. Three jobs, simple mode first: explain the as-is code with the agent; start a target with
   the agent (proposals read "PROPOSED - NOT APPLIED"); adopt the code through `init` and
   `init --adopt` (AD-266), with no second path. A marked area gets `label` and
   `responsibilities` as an agent decision. Slices 1 and 2a build Overview, Map, Explore and Report.
3. Backend `archkeel.studio`, four components in `docs/architecture/contracts/studio.json`: `api`
   (routes, typed answers, no I/O), `graph` (pure call graph; only `workspace` requires it, so
   `server` cannot build one), `workspace` (the explore child, into a private 0700 folder of this
   run below the explore cache; deleted at the end), `server` (HTTP, token). The package imports no
   other component: the CLI injects the explore command, the contract state, the snapshot decoder
   and the module owner of the contract. AD-292 adds `agent` (read-only, no key). Planned: `proposals` (the only writer). Outside edits: `Command.STUDIO` in
   `ir/model.py`; the embed lines of item 8.
4. API: `GET /api/v1/state` and `GET /api/v1/graph` (call graph; `components_from`: contract or
   explore layout), pinned by `schema/studio-api-1.1.schema.json`; `POST /api/v1/chat` (AD-292) is the only POST; PUT, PATCH, DELETE and any other POST get 405.
   The graph says `graph: null` until the run is done. `/files/<name>` serves snapshot pages,
   `/ui/<name>` the shell files.
5. Versions: with `additionalProperties: false`, a new field or route is a new minor with a new
   schema file; a removed or renamed field is a new major. The client errors on a mismatch.
6. Security: 127.0.0.1 on a free port. A `secrets.token_urlsafe(32)` token in the start URL,
   then an HttpOnly SameSite=Strict cookie for each port. Another `Host` header or no token
   gives 403. The shell CSP allows only `'self'`; the Explorer pages allow no other origin.
   **Hard gate** before any write route (proposals): the iframe gets a `sandbox` without
   `allow-same-origin`, the report pages come from another origin or port, and the
   postMessage bridge is the only channel between the two.
7. Frontend: TypeScript and Preact 10.29.8 (MIT, no dependency, pinned exact), built by the
   esbuild 0.28.2 of `tools/browser-runtime` into the committed `studio/ui/studio.js`; the
   wheel ships the bundle, not its sources, and users need no Node. `vocabulary.ts` is
   generated from the enums of `studio.api`. One small store, no Markdown. Always dark.
8. Embed (view Report): the shell loads the unchanged Explorer page with `?embed`. The parameter
   sets `data-embed` (`report-canvas.js`, kept by `flow.js`); `report-canvas.css` then hides the
   report chrome and fixes the canvas to the frame. A selection posts `{kind: "component-selected",
   id, label}` to the parent, same origin only. The shell copies its tokens into the `--ak-*`
   variables of the frame. Without `?embed` the page does not change.
9. Enforced: `studio` requires nothing, so an import of `cli`, an analyzer or `check` fails
   `REQUIRES-COMPLETE`; only `workspace` imports `subprocess` and only `server` imports
   `http`. `docs/architecture/studio-ui.toml` checks the UI: only `api.ts` calls `fetch`, views
   never import views, components never import the client, Preact is the only package.
10. Launcher: while a server runs, the CLI keeps `studio.json` (pid, URL, port; mode 0600) in the
    explore cache folder of the root; `Studio` writes no file. A start reuses a server only if
    its stored URL answers with the Studio login redirect; `--stop` signals (SIGTERM) after the
    same check and waits for the URL to go. A live pid is no proof. `--idle-exit` counts requests.

**Rejected.** React 19.3.1 (69,148 B gzip; Preact 10.29.8 + hooks: 5,668 B; a second scheduler), web
components (hand-made state), React Flow, a state library, an MCP server, 0.0.0.0, a fixed port, a
server-rendered embed page. No demo-catalog row: `studio` runs until stopped.

**Limits.**
- Explore runs at each start (95 to 124 s on 1185 files); cache reuse is issue #814.
  Progress is elapsed seconds: explore reports no phase while it runs.
- Flows says "Not built"; slice 3 (#816) plays the AD-289 tour. Slice 2b: chat, Discussion panel.
- The graph counts call sites (a partly resolved call with two candidates is one claim), has no
  module-level call, counts a call to a target outside the scan apart (neither edge nor unknown),
  and keeps the true count of unknown calls with the first 4. The lens shows 1 hop. A link to a
  detail page leaves the embed mode (Report).
- A reused server keeps its scope. Two starts between `running_studio` and `write_state` (tens of
  ms) both run explore; `--stop` finds the last file, the other runs until `--idle-exit`.
- Windows `--stop` skips the cleanup: the explore child and the `studio-*` folder can stay behind.
- Only the `subprocess` and `http` imports are scoped; other process and file-write APIs are
  not. Tests check that the repository stays unchanged. Type-only imports stay undecided.

**Checks.** `tests/test_studio*.py`, `tests/smoke_test.py`.
