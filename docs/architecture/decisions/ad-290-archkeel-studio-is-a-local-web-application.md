# AD-290 ArchKeel Studio is a local web application

**Status.** Accepted. Owner decisions of 2026-11-03, epic #783. Amends the "server" part of the
rejected lines of AD-284 and AD-285. The Explorer stays the only architecture renderer.

**Decision.**
1. `archkeel studio [--root PATH] [--no-open]` with the scope options of explore (`--language`,
   `--source`, `--namespace`, `--tsconfig`) serves a local app; the CLI opens the browser.
   Studio is parallel to the static report, which stays the first-class CI and Pages artifact.
2. Three jobs, simple mode first: explain the as-is code with the agent; start a target with
   the agent (proposals read "PROPOSED - NOT APPLIED"); adopt the code through `init` and
   `init --adopt` (AD-266), with no second path. A marked area gets `label` and
   `responsibilities` as an agent decision. Slice 1 builds Overview and Explore.
3. Backend `archkeel.studio`, three components in `docs/architecture/contracts/studio.json`:
   `api` (routes, typed state, no I/O), `workspace` (the explore child, into a private 0700
   folder of this run below the explore cache; deleted at the end), `server` (HTTP, token).
   The package imports no other component: the CLI injects the explore command and the
   contract state (`archkeel.toml` loads and its contract parses). Planned: `agent` (a port for
   `claude -p` or `codex exec`, read-only, no key) and `proposals` (the only writer).
4. API: `GET /api/v1/state`, pinned by `schema/studio-api-1.0.schema.json`; POST, PUT, PATCH
   and DELETE get 405. Explore starts with the server, so slice 1 needs no write route.
   `/files/<name>` serves the snapshot pages; `/ui/<name>` serves only the shell files.
5. Versions: the schema has `additionalProperties: false`, so a new field is a new minor with a
   new schema file, and a removed or renamed field is a new major. The client compares
   `api_version` and shows an error on a mismatch.
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
8. Embed: the shell loads the unchanged Explorer page with `?embed`. The present parameter
   sets `data-embed` (`report-canvas.js`); `flow.js` keeps it in the URL. `report-canvas.css`
   hides the report header, the other sections, the brand, Open, theme and Fullscreen, and
   fixes the canvas to the frame. The shell shows the frame after it loads and copies its
   tokens into the `--ak-*` variables. A selection posts `{kind: "component-selected", id,
   label}` to the parent, same origin only. A page without `?embed` does not change.
9. Enforced: `studio` requires nothing, so an import of `cli`, an analyzer or `check` fails
   `REQUIRES-COMPLETE`; only `workspace` imports `subprocess` and only `server` imports
   `http`. `docs/architecture/studio-ui.toml` checks the UI: only `api.ts` calls `fetch`, views
   never import views, components never import the client, Preact is the only package.

**Edits outside the package.** `Command.STUDIO` in `ir/model.py`; the embed lines of item 8.

**Stack comparison.** A counter button, minified by esbuild 0.28.2, on 2026-11-03. The Studio
bundle is 20,227 B (8,152 B gzip). Preact 11 is 5 weeks old; 10.x is mature.

| Stack | min | gzip | Packages | Cost |
|---|---|---|---|---|
| React 19.3.1 + react-dom | 223,607 B | 69,148 B | 3 (MIT) | 12x Preact; a second scheduler |
| Preact 10.29.8 + hooks | 13,580 B | 5,668 B | 1 (MIT) | One pinned package; React-like API |
| Web components | 417 B | 291 B | 0 | Hand-made rendering and state for each view |

**Rejected.** A web framework, React Flow, a state library, an MCP server, 0.0.0.0, a fixed
port, a server-rendered embed page. No demo-catalog row: `studio` runs until Ctrl-C.

**Limits.**
- Explore runs at each start (95 to 124 s on 1185 files); cache reuse is issue #814.
  Progress is elapsed seconds: explore reports no phase while it runs.
- Flows says "Not built"; the next slice lists the view specs and plays the AD-289 tour.
- Slice 2: system-map cards, the top bar, the Discussion panel, component data beyond id and
  label. A link to a detail page leaves the embed mode.
- Only the `subprocess` and `http` imports are scoped; other process and file-write APIs are
  not. Tests check that the repository stays unchanged. Type-only imports stay undecided.

**Checks.** `tests/test_studio.py`, `tests/test_studio_browser.py`, `tests/smoke_test.py`.
