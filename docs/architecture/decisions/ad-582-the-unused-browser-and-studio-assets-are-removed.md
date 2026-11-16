# AD-582: The unused browser and Studio assets are removed

Status: accepted (owner decision). Part of #880. It supersedes AD-242, AD-290, AD-492 for the tree.

## Context
`src/archkeel/render/assets` (Explorer: `flow.js`, `explorer.runtime.js`, graph scene and protocol,
ELK) and `src/archkeel/studio/ui` (Studio UI, `studio.js`) were loaded by the Python report renderer
and the Studio server. AD-432 (#1131) deleted both. In 5.0 no shipped path loads these files:
the Rust report crate writes its page from `native/report/assets`, and `explore` and `studio` give
a typed refusal. They were kept alive by self-checks (`browser.toml`, `studio-ui.toml`, their pins),
a build tool, a Chromium snapshot harness and Make targets.

## Decision
Remove every file that only these assets use. Git history keeps them. They come back when `explore`
and Studio are ported to the core (5.1).

Removed: both asset trees (except `archkeel-mark.svg`, which the plugin package uses), the build
tool `tools/browser_runtime.py` and its bundle scripts, the DOM snapshot harness and its fixtures,
the browser and Studio self-check contracts and pins, the Make targets `browser-runtime-generate`,
`browser-runtime-check`, `browser-graph-generate`, `browser-graph-check`,
`browser-architecture-check`, and the tests that guarded only these files. The `browser` pytest marker
is removed with the last Chromium test.

Kept: `tools/browser-runtime/package.json` with the pinned TypeScript compiler (the standard-library
catalog check and the compiler check read it), `archkeel-mark.svg`, `schema/studio-api-*.schema.json`
(wire schemas that the wheel ships), the TypeScript fixtures. The collector tests that read the
Studio sources as a TSX corpus read the fixtures only.

## Price
The own self-check has no browser (1 rule) and no Studio UI (7 rules) part. Both were UNKNOWN. The
gap pins of those parts go with them.
