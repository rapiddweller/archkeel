# AD-788: A repository file outside the scan roots that replaces a global withholds its proof

Status: accepted (owner decision 2026-11-17, options A and B of #1546). Part of #880. Closes #1546
and #1674 (amendment of the lead review of #1668).
It amends premise 4 of AD-540.

## Context
`boot.ts` at the root of the repository, outside the scan root `src`, writes
`window.open = hidden` with a function of component `b`. Component `a` calls `window.open()`, and
the collector proved `open` native: `REQUIRES` gave PASS. Premise 4 of AD-540 said only that code
outside the scan roots hands in no global or platform object. No narrow rule is sound: any code in
the page, also outside the repository, can import an exported function and install it as a global.
A rule that withholds every global proof is sound but makes every TypeScript rule UNKNOWN.

## Decision
1. **Premise (A).** The stated assumption of each TypeScript scan reads "code outside the scan roots
   hands in no global or platform object and replaces no global" (`records.rs`). The text header,
   the JSON key `premise` and the report show it wherever they show the assumption now.
2. **Repository guard (B).** `script_outside.rs` reads each JavaScript, TypeScript and HTML file
   (inline scripts) of the repository outside the scan roots. It does not read test files (the
   test-source rule of AD-313), declarations, version-control metadata (`.git`, `.hg`, `.svn`),
   Python environments and tool caches, and installed packages: third-party code under the
   premise. Every other hidden folder is read.
   `script_outside_forms.rs` finds each write that replaces a global:
   - `window.x =` and the other window names (`globalThis`, `self`, `frames`, `top`, `parent`,
     `global`, `opener`), also with a literal key, `+=` and `++`;
   - an assignment to a name that the file does not declare;
   - a top-level binding of a classic script (no top-level `import` or `export`, no
     `type="module"`);
   - `Object.assign`, `Object.defineProperty(ies)`, `Object.setPrototypeOf`, `Reflect.set`,
     `Reflect.defineProperty`, `Reflect.setPrototypeOf` on a window name, and
     `window.__defineGetter__` or `__defineSetter__`.
   - a member patch of a global that the file does not declare (`Math.max = f`,
     `Object.assign(Math, …)`, `console.__defineGetter__(…)`), unless the value is a literal.
   `script_patch.rs` reads the same member patches in each scanned file (#1674). A patch writes a
   path below the global (`max`; `body.style.overflow`; a key that is no literal ends the path).
   It withholds the proof of a use whose path is below it or above it (`Math.max(…)`, `Math` as a
   value); a use of another member keeps it (`Math.min`), and so does the written target itself.
   The gap reads "Script global Math is patched by a member write" (or "by a file outside the scan
   roots") and cites the use and the write.
3. **Effect.** A hit withholds the native proof of its name (`script_global.rs`). The use gets the
   gap "Script global X is replaced by a file outside the scan roots", which cites the use and the
   write (file and line). A write whose name the guard cannot read (`window[k] =`) or a file that it
   cannot parse withholds every global ("can be replaced"). A file that it cannot read (size or
   input limit) withholds every global with the cause "the global-writer guard cannot read F …"
   and no citation of F. There is no file limit: 50 000 small files outside the roots took 6.9 s
   and 121 MB in all (graphql-js alone 0.6 s).

## Soundness
The guard reads only what the repository holds; code outside the repository stays under the
premise, and the premise is printed with each verdict, so no PASS rests on an unstated assumption.
Inside the repository a counterexample to the premise is no longer silent. The reader is
syntactic and local to the file: a name that the file declares anywhere is not free, so a write to
it in another scope is missed. That is a gap of the guard, not of the premise: the premise still
covers it, and the report names the premise.

## Price
graphql-js (67 gaps) and the fixtures F, H, H-uml, L-nest are unchanged. Explorer scripts: 617
gaps before and after the guard; 451 to 540 with the amendment on main `cccb6aeaa` (`flow.runtime.js:1`, a built copy in
the repository, and `flow.js` itself write members of `document` and `location`, for example
`location.hash = encodeURIComponent(id)` at `flow.js:2242`; a use that the collector records only
as `document` counts as a use of the whole global). No rule changes.

## Tests
`native/typescript/src/script_outside_tests.rs` (the plant, 11 forms, an unknown name, 6 quiet
files, 5 files that are not read, the cited places); `tests/test_collector_false_pass_ts_outside_writer.py`
(the plant through the release core: UNKNOWN with the file in the repository, PASS under the printed
assumption without it); `script_member_patch_tests.rs` and
`tests/test_collector_false_pass_ts_member_patch.py` (#1674: the patch in a scanned file and outside
the roots, a literal and a local object keep the proof).
