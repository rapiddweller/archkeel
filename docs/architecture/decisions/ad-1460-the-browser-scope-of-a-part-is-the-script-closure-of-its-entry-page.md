# AD-1460: The browser scope of a part is the script closure of its entry page

Status: accepted. Amends AD-540 (the premise guard for globals), AD-788 and the guard of #1546.

## Why

The guard reads each JavaScript, TypeScript and HTML file of the repository outside the scan roots. One write there
that replaces a global withholds the native proof of that global. For the Studio part (`studio/archkeel.toml`, the root
is the repository) this read 184 gaps from files that no browser loads for Studio: three test fixtures and a vendored
grammar (one write with an unreadable name holds every global), `flow.runtime.js` (the report page, 23 gaps) and 14 Node
preloads from a fixture `package.json`. A scope cannot be a hand list: a list drifts from the page, and an exclusion by
folder name can hide a file that ships.

## Decision

1. A TypeScript part states `browser_entry` (an HTML page) and optionally `browser_assets` (folders, default the folder
   of the page). The core derives the browser files: the page, its `<script src>` and modulepreload links, and from each
   loaded script the `import`, `export … from`, `import("…")`, `importScripts("…")` and `new Worker("…")` with a
   literal path, transitively. A path that starts with `/` is searched in each assets folder in order; a relative path
   is resolved against the URL of the file that names it. A URL outside the repository is code outside the repository,
   which the premise covers.
2. The guard reads the loaded files outside the scan roots, and nothing else. A loaded file stays in whatever its place.
   Node preloads are not read for such a part: they run in no browser.
3. Nothing narrows silently. A missing entry or assets folder refuses the run. A reference that cannot be followed (a
   path in no folder, a bare name, a path that is no literal, a file that cannot be read or parsed, more than 2,000
   files) is the cause of the run: no global has a native proof, and the gap names the file and the reference.
4. A part without `browser_entry` behaves as before.

The collection request carries `resolver.browser` (`entry`, `assets`) only when it is stated, like `bundler`. The frame
schema is regenerated.

## Rejected

- A key that lists the files of the page: a second source of truth for what the page loads.
- Skipping `fixtures/` by name: it hides a file that ships and decides by a string.
- Reading `<script src>` against the folder of the page only: the Studio server serves one URL space from two folders.

## Counter-examples (`native/typescript/src/browser_entry_tests.rs`, `native/collect/src/config_tests.rs`)

- A file that the entry loads and that writes `window.open` still holds `open`. A file that no entry loads and that writes
  `window.close` does not hold `close`; without an entry both hold (the control).
- `./deep.js` is relative to the URL of the file that names it, not to the page.
- `import("/a" + x)`, a path in no folder, `import "lodash"` and a worker path that is no literal each hold every global.
- A missing entry refuses; assets without an entry, a path with `..` and a non-TypeScript part are invalid.

## Not done

The loaded ELK bundle (`elkjs-0.12.0.bundled.js`) stays unproven: it spawns a worker with a path that is no literal
and the guard cannot bound its writes (see the owner note on ELK). The two layout scripts that Studio now scans bring
their own gaps of the form "namespace effects are not statically bounded" (the IIFE `(function (global) {…})(window)`
form); the same form holds the browser part.
