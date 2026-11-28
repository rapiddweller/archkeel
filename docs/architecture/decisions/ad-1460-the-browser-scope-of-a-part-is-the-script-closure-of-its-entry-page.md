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
   loaded script the `import`, `export … from`, `import("…")`, `importScripts("…")`, `new Worker("…")` and
   `serviceWorker.register("…")` and `addModule("…")` with a literal path, transitively. A page names files with
   `<script src>`, `<iframe src>`, `<frame src>`, `<embed src>`, `<object data>` and modulepreload links, and it runs code
   that names more files the same way: an inline script, an `on…` attribute and a `javascript:` address. A tag is read
   as a browser reads it (a quoted attribute can hold `>`; `<` before a space is text; a comment and a `<style>` hold no
   tag). A path that starts with `/` is searched in each assets folder in order; a relative path
   is resolved against the URL of the file that names it. A URL outside the repository is code outside the repository,
   which the premise covers.
2. The guard reads the loaded files outside the scan roots, and nothing else. A loaded file stays in whatever its place.
   Node preloads are not read for such a part: they run in no browser.
3. Nothing narrows silently. A missing entry or assets folder refuses the run. A reference that cannot be followed (a
   path in no folder, a bare name, a path that is no literal, a `<base>` or an import map, an `srcdoc` page, a script element that code
   creates, a `document.write`, code with a syntax error node (the tree can hide a reference), a file that cannot be read or parsed, more than 2,000 files) is the cause of the run: no global has a native proof, and the gap names the file and the reference.
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
- `document.createElement("script")`, `document.write` and a service worker path that is no literal hold every global
  (a loaded file can load any file by them); a literal service worker path is followed; `createElement("div")` is no script, and a tag that is no literal is not examined (see "Not done").
- A `<base>` element, an import map and an `srcdoc` page hold every global. `<iframe src>`, `<frame>`, `<embed>`, `<object data>`
  and an `addModule` path are followed.
- Code in the page is read like a script (Codex, round 1): `<script type=module>import '/w.js'</script>`, an `onclick`
  attribute, a `javascript:` address. Quoted `>` in an attribute (`<script data-note=">" src=/w.js>`), `x < y <script …>`,
  a comment and a `<style>` before the script do not hide it. Code that does not parse in full holds every global.
- A missing entry refuses; assets without an entry, a path with `..` and a non-TypeScript part are invalid.

## Not done

A script element whose tag is chosen at run time (`document.createElement(tag)`) is not examined. A helper such as the
`element(tag)` of `studio-dom.ts` is the plain form of a page, and holding it would keep Studio UNKNOWN for a form that
no caller uses with `"script"`. A caller that builds a script element through such a helper and loads a repository file
that no entry names is a false PASS that this record accepts as a documented limit. The owner decides if it is too wide.

A file that a loaded script fetches and runs through `eval` or `Function` is not followed. The guard already holds every
global for a loaded file outside the scan roots that runs code (`eval`, `Function`); a scanned file keeps the rule of the
scan. A server that adds scripts the page does not name is outside the repository.

The loaded ELK bundle (`elkjs-0.12.0.bundled.js`) stays unproven: it spawns a worker with a path that is no literal
and the guard cannot bound its writes (see the owner note on ELK). The two layout scripts that Studio now scans bring
their own gaps of the form "namespace effects are not statically bounded" (the IIFE `(function (global) {…})(window)`
form); the same form holds the browser part.
