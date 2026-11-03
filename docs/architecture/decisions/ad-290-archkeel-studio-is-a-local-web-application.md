# AD-290 ArchKeel Studio is a local web application

**Status.** Accepted. Owner decisions of 2026-11-03, epic #783. Amends the "server" part of the
rejected lines of AD-284 and AD-285. The Explorer stays the only architecture renderer.

**Decision.**
1. `archkeel studio [--root PATH] [--no-open]` serves a local app and opens the browser. The
   skill starts it; the owner talks to the own agent session beside it.
2. Studio is parallel to the static report. The report stays first class: the CI and Pages
   artifact with contract, deviations, PASS or FAIL and the explorable architecture.
3. Three jobs, simple mode first: explain the as-is code with the agent (Overview, Explore,
   Flows, tour); start a target with the agent (proposals read "PROPOSED - NOT APPLIED"); adopt
   the code as the target through `init` and `init --adopt` (AD-266), with no second path.
   Marking an area with `label` and `responsibilities` writes an agent decision for the
   architect. Slice 1 builds Overview and Explore; the other pages say "Not built".
4. Backend `archkeel.studio`, three components in `docs/architecture/contracts/studio.json`:
   `api` (routes, typed state, no I/O), `workspace` (the explore child into the explore cache
   folder of AD-285; reads its files by exact name), `server` (HTTP, token, 127.0.0.1). The
   package imports no other component: the CLI injects the explore command and the contract
   state (`load_config`: no file, a failed load, a load). Planned: `agent` (a port; the adapter
   starts the CLI of the owner, `claude -p` or `codex exec`, read-only; no key stored) and
   `proposals` (the only writer, after an architect click, through the amendment path).
5. API: `GET /api/v1/state`, pinned by `schema/studio-api-1.0.schema.json`; POST, PUT, PATCH
   and DELETE get 405. The workspace starts explore when the server starts, so slice 1 needs
   no write route. The proposals endpoint will be the one write route. `GET /files/<name>` serves the
   snapshot pages; `/ui/<name>` serves only the four shell files.
6. Security: 127.0.0.1 on a free port, no host option. A `secrets.token_urlsafe(32)` token in
   the start URL, then an HttpOnly SameSite=Strict cookie for each port. Another `Host` header
   or no token gives 403. The shell CSP allows only `'self'`; the Explorer pages get inline
   script and style, and no other origin.
7. Frontend: TypeScript and Preact 10.29.8 (MIT, no dependency, pinned exact), built by the
   esbuild 0.28.2 of `tools/browser-runtime` into the committed `studio/ui/studio.js` that
   ships in the wheel; users need no Node. `tools/browser_runtime.py` generates `vocabulary.ts`
   from the enums of `studio.api` and checks it. The Explorer is an `<iframe>` island. One
   small store, no state library, no Markdown, no network but the own server. Always dark.
8. Enforced: `studio` requires nothing, so an import of `cli`, an analyzer or `check` fails
   `REQUIRES-COMPLETE`; only `workspace` imports `subprocess` and only `server` imports
   `http`. `docs/architecture/studio-ui.toml` checks the UI: only `api.ts` calls `fetch`, views
   never import views, components never import the client, Preact is the only package. Tests
   check what no rule kind sees: the repository stays unchanged, and only the cache is written.

**Edits outside the package.** `ir/model.py` gains `Command.STUDIO`, the command vocabulary of
the CLI. `render/html.py` is unchanged: the Preact shell replaced the server-rendered shell.

**Stack comparison.** A counter button, minified by esbuild 0.28.2, measured 2026-11-03:

| Stack | min | gzip | Packages | Cost |
|---|---|---|---|---|
| React 19.3.1 + react-dom | 223,607 B | 69,148 B | 3 (MIT) | 12x Preact; a second scheduler |
| Preact 10.29.8 + hooks | 13,580 B | 5,668 B | 1 (MIT) | One pinned package; React-like API |
| Web components | 417 B | 291 B | 0 | Hand-made rendering and state for each view |

The slice-1 bundle is 18,778 B (7,636 B gzip). Preact 11 is 5 weeks old; 10.x is mature.

**Rejected.** A Python web framework: a dependency for one GET route. React Flow or a state
library: the Explorer draws the graph. An MCP server: a second session. A copy-prompt button:
no answer comes back. 0.0.0.0 or a fixed port. A demo-catalog row: a catalog row runs a
command to its end, and `studio` is a server that runs until Ctrl-C; the tests below are the
evidence.

**Limits.**
- Explore runs at each start (about 95 s on 1185 files); cache reuse by repository state is an
  open issue. Progress is elapsed seconds: explore reports no phase while it runs.
- Flows says "Not built". The next slice lists the view specs and plays the tour of AD-289.
- Slice 2 builds the system-map cards and the selected-component panel of Overview, the top
  bar, an Explore canvas that fills the viewport, and the Discussion panel.
- Type-only imports are undecided for symbol rules: no UI `interface_boundary` rule.

**Checks.** `tests/test_studio.py`, `tests/test_studio_browser.py` (Chromium at 1440x900 and
800x600), `make browser-architecture-check`, `make self-validate`.
