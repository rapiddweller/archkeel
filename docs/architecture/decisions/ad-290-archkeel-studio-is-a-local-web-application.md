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
   `responsibilities` as an agent decision. Slices 1 and 2a build the first page (the Briefing, called Overview at first), Map, Explore and Report. Slice 2b adds the Stories view (the player) and the chat panel in the Map and the lens. The UI has four levels, as in the concept (section 10 and 11): the Map shows components; a click on a card opens that component (its modules on plates by package, with the other components as stubs at the sides); a click on a module opens its functions (the other modules as stubs); a click on a function opens the lens. The URL names the level: `#/map`, `#/component/<n>[/<package>]`, `#/module/<n>`, `#/explore/<function>`. One location bar sits in the same place on every page (architecture, component, packages, module file, function); each part goes up to its level, and Esc goes one level up. Every level has a side panel that starts with "You are here" and an Up link. The component and module levels are calm at rest: cards on plates, no call lines. A hover or a click on a card (the click pins it, Esc clears the pin before it goes up, a double click or Enter opens the card) draws only the lines of that card, routed through the gutters between the cards with a halo, and dims every card that is not connected. The side panel then lists each connected card with its module, file, line and proof, and a row lights its line. A stub shows the module path and, while a card has the focus, the names of the functions on the other side. At rest every stub has one faint line to a port on the nearest plate; a stub that does not touch the focused card is dimmed and shows its count only. When the page is one package of a component, the other packages of the component are stubs too, named by their package path. A focused line ends with a port dot on the edge of its card and carries one small dot that runs from the caller to the callee (about 2 s a run, a chevron with reduced motion). The number on a function card is its distinct neighbor functions, and the side panel lists exactly those. At the default fit no text is below 10 px: a package that does not fit the first screen (8 modules, 16 functions) folds into a tile that opens it. A drill zooms from the clicked card in 250 ms, going up zooms out, and reduced motion shows no zoom. The levels are derived in the browser from `GET /api/v1/graph`; the API has no new field. The first page is the Briefing: measured numbers (modules, functions, the share of resolved calls, unknown calls, from the `totals` and `snapshot` of the graph answer), at most six sentences of what stands out (most called functions, component cycles, largest gaps, components with the most unknown calls, the contract), the five newest stories and a question field that opens the chat. Each sentence has a "Show" link to the place it names; nothing is an opinion. A click on a card selects it and shows what the panel knows; a double click or Enter opens it; Esc clears the selection first. Cards carry no tooltip and no cut text: a card grows to its name, and the panel holds the rest. The navigation has one item, "Architecture", for the four levels (`#/map` is the entry; `#/explore/<fn>` and the other level URLs stay valid), then Stories; Impact and Target / Diff show as "Planned": muted, no link, the tooltip says "not built yet". The static report is not a page of the workspace: it is a secondary link, because the Explorer page keeps its own look.
3. Backend `archkeel.studio`, four components in `docs/architecture/contracts/studio.json`: `api`
   (routes, typed answers, no I/O), `graph` (pure call graph; only `workspace` requires it, so
   `server` cannot build one), `workspace` (the explore child, into a private 0700 folder of this
   run below the explore cache; deleted at the end), `server` (HTTP, token). The package imports no
   other component: the CLI injects the explore command, the contract state, the snapshot decoder
   and the module owner of the contract. AD-292 adds `agent` (read-only, no key). Planned: `proposals` (the only writer). Outside edits: `Command.STUDIO` in
   `ir/model.py`; the embed lines of item 8.
4. API: `GET /api/v1/state` and `GET /api/v1/graph` (call graph; `components_from`: contract or
   explore layout), pinned by `schema/studio-api-1.1.schema.json`; `POST /api/v1/chat` (AD-292) is the only POST; PUT, PATCH, DELETE and any other POST get 405.
   Slice 2b adds read-only `GET /api/v1/stories`, `GET /api/v1/stories/<id>` (the result of `archkeel view check`, AD-291, run on the snapshot of this run) and `GET /api/v1/draft?from=<function>` (a draft spec from `story trace`; nothing is written). The specs are the `*.story.json` files in `<root>/.archkeel/stories/` (committed, mark `repository`) and in `stories/` below the explore cache folder of the root (outside the folder of the run, mark `local`); the repository wins on an equal id. A spec that names another snapshot is checked by node name against the current one (AD-291). The CLI injects the checker and the draft. No route writes: "Pin to story" shows the draft, because the hard gate of item 6 comes first.
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
   id, label}` to the parent. Since AD-292 the page is sandboxed (opaque origin): it posts to
   target `*` and the shell accepts a message only when `event.source` is the frame window. The
   shell cannot reach the frame document, so it posts its colour tokens, and the page applies them (`studio-tokens`, accepted only from the parent). A navigation that starts inside the frame is cross-site for the SameSite cookie and gets 403 (checked in Chromium); the embed shows no link to another page. Without `?embed`
   the page does not change.
9. Enforced: `studio` requires nothing, so an import of `cli`, an analyzer or `check` fails
   `REQUIRES-COMPLETE`; only `workspace` imports `subprocess` and only `server` imports
   `http`. `docs/architecture/studio-ui.toml` checks the UI: only `api.ts` calls `fetch`, views
   never import views, components never import the client, Preact is the only package.
10. Launcher: while a server runs, the CLI keeps `studio.json` (pid, URL, port; mode 0600) in the
    explore cache folder of the root; `Studio` writes no file. A start reuses a server only if
    its stored URL answers with the Studio login redirect; `--stop` signals (SIGTERM) after the
    same check and waits for the URL to go. A live pid is no proof. `--idle-exit` counts requests.

**Rejected.** React 19.3.1 (69,148 B gzip; Preact 10.29.8 + hooks: 5,668 B), web components, React
Flow, a state library, an MCP server, 0.0.0.0, a fixed port, a server-rendered embed page. No
demo-catalog row: `studio` runs until stopped.

**Limits.**
- Explore runs at each start (95 to 124 s on 1185 files); cache reuse is issue #814.
- The graph counts call sites (a partly resolved call with two candidates is one claim), has no
  module-level call, counts a call to a target outside the scan apart (neither edge nor unknown),
  and keeps the true count of unknown calls with the first 4. The lens shows 1 hop. A link to a
  detail page leaves the embed mode (Report).
- A reused server keeps its scope. Two starts between `running_studio` and `write_state` (tens of
  ms) both run explore; `--stop` finds the last file, the other runs until `--idle-exit`.
- Windows `--stop` skips the cleanup: the explore child and the `studio-*` folder can stay behind.
- Only `subprocess` and `http` imports are scoped; tests check that the repository stays
  unchanged. Type-only imports stay undecided.

**Checks.** `tests/test_studio*.py`, `tests/smoke_test.py`.
