# AD-788: A repository file outside the scan roots that replaces a global withholds its proof

Status: accepted (owner decision 2026-11-17, options A and B of #1546). Part of #880. Closes #1546.
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
   test-source rule of AD-313), declarations, installed-package directories and hidden directories.
   `script_outside_forms.rs` finds each write that replaces a global:
   - `window.x =` and the other window names (`globalThis`, `self`, `frames`, `top`, `parent`,
     `global`, `opener`), also with a literal key, `+=` and `++`;
   - an assignment to a name that the file does not declare;
   - a top-level binding of a classic script (no top-level `import` or `export`, no
     `type="module"`);
   - `Object.assign`, `Object.defineProperty(ies)`, `Object.setPrototypeOf`, `Reflect.set`,
     `Reflect.defineProperty`, `Reflect.setPrototypeOf` on a window name, and
     `window.__defineGetter__` or `__defineSetter__`;
   - a member write of an undeclared global (`Math.max = f`), unless the value is a literal.
3. **Effect.** A hit withholds the native proof of its name (`script_global.rs`). The use gets the
   gap "Script global X is replaced by a file outside the scan roots", which cites the use and the
   write (file and line). A write whose name the guard cannot read (`window[k] =`), a file that it
   cannot read or parse, and more than 4000 files withhold every global ("can be replaced").

## Soundness
The guard reads only what the repository holds; code outside the repository stays under the
premise, and the premise is printed with each verdict, so no PASS rests on an unstated assumption.
Inside the repository a counterexample to the premise is no longer silent. The reader is
syntactic and local to the file: a name that the file declares anywhere is not free, so a write to
it in another scope is missed. That is a gap of the guard, not of the premise: the premise still
covers it, and the report names the premise.

## Price
Measured before and after (graphql-js v16.15.0, the TypeScript fixtures F, H, H-uml, L-nest and
the Explorer scripts): see the PR. A repository with build scripts that write globals loses the
proof of those names only.

## Tests
`native/typescript/src/script_outside_tests.rs` (the plant, 11 forms, an unknown name, 6 quiet
files, 5 files that are not read, the cited places); `tests/test_collector_false_pass_ts_outside_writer.py`
(the plant through the release core: UNKNOWN with the file in the repository, PASS under the printed
assumption without it).
