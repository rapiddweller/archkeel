# AD-788: A repository file outside the scan roots that replaces a global withholds its proof

Status: accepted (owner decision 2026-11-17, options A and B of #1546). Part of #880. Closes #1546,
#1674 and #1712 (lead review of #1668, audit 2). It amends premise 4 of AD-540.

## Context
`boot.ts` at the root, outside the scan root `src`, writes `window.open = hidden` with a function of
component `b`; `a` calls `window.open()`, and `REQUIRES` gave PASS. Premise 4 of AD-540 said only
that code outside the scan roots hands in no global or platform object. No narrow rule is sound
(any code of the page can install an exported function as a global); withholding every global
proof is sound but makes every TypeScript rule UNKNOWN.

## Decision
1. **Premise (A).** The assumption of each TypeScript scan reads "code outside the scan roots hands
   in no global or platform object and replaces no global" (`records.rs`): text header, JSON
   `premise`, report.
2. **Repository guard (B).** `script_outside.rs` reads each JavaScript, TypeScript and HTML file
   (inline scripts) of the repository outside the scan roots, but no test file (AD-313), no
   declaration, no version-control metadata (`.git`, `.hg`, `.svn`), no Python environment or
   tool cache, and no installed package (third-party code under the premise). Every other hidden
   folder is read. Each program is read twice:
   - with the write detector of the scan (`script_outside_detector.rs`, #1712): a direct form (a
     window alias or name that leaves, `eval`, `Function`, a reflective call on a window), an
     amplifier form in a file with a host entry, and a write with no path withhold every global;
     each path written on the global object (also through an alias, a pattern, a `for` target)
     and each global of a classic script withholds its first name;
   - with `script_outside_forms.rs`: `window.x =` (and `globalThis`, `self`, `frames`, `top`,
     `parent`, `global`, `opener`), an assignment to an undeclared name, a top-level binding of a
     classic script, `Object.assign/defineProperty(ies)/setPrototypeOf`, `Reflect.set/
     defineProperty/setPrototypeOf` and `__defineGetter__/__defineSetter__` on a window name, and
     a member patch of an undeclared global (`Math.max = f`) unless the value is a literal.
   A stated generated copy is not read (`script_outside_generated.rs`): its last lines state
   `// Generated from S; source-sha256=H`, `// Owner: G`, `// Check: C`, each S (relative to the
   copy) is a scanned file with SHA-256 H, and G and C are files. Its writes are those of S; the
   premise adds "and a stated generated copy is the code of its sources"; a later edit of the copy
   is what C checks. A statement that does not hold leaves the copy read. The test-file rule is the
   one of the test exclusion (`is_test_source`); it does not name `fixtures`, and a wider rule
   would drop production folders of that name from a scan, weaker than 4.0.1.
3. **Member patches (#1674).** `script_patch.rs` reads member patches in each scanned file too. A
   patch writes a path below the global (`max`, `body.style.overflow`; a key that is no literal
   ends it). It withholds a use below or above that path (`Math.max(…)`, `Math` as a value); a use
   of another member (`Math.min`) and the written target keep their proof.
4. **Effect.** A hit withholds the native proof: "Script global X is replaced by (can be replaced
   by, is patched by) a file outside the scan roots" or "… is patched by a member write", citing
   the use and the write. A file that the guard cannot read (size or input limit) withholds every
   global with the cause "the global-writer guard cannot read F …" and no citation of F. There is
   no file limit: 50 000 small files outside the roots took 6.9 s and 121 MB (graphql-js 0.6 s).

## Soundness
The guard reads what the repository holds with the detector that decides scanned files, so a
form that blocks a proof inside the scan blocks it from outside too; the second reader adds named
forms that the detector reads as unknown. Code outside the repository stays under the premise,
which is printed with each verdict. Precision limit of the detector, not of soundness: a use that
the collector records only as the global (`document`) counts as a use of the whole global.

## Price
graphql-js (67 gaps) and the fixtures F, H, H-uml, L-nest are unchanged; no rule changes. Explorer
scripts (root = this repository): 617 before and after the guard; 451 to 540 with #1674 (`flow.js`
writes `location.hash`, `document.body.style.overflow`); 540 to 1096 with #1712: three vendored or
built files outside the roots hold direct forms, so every global "can be replaced"
(`fixtures/L-nest-realworld/resolver-inputs/slug/slug.js:75`, `elkjs-0.12.0.bundled.js:4690`,
`flow.runtime.js:1`). With the stated copy, `flow.runtime.js` is not read: 1096 to 1096, because
the vendored `elkjs-0.12.0.bundled.js` (which runs in the page) and the fixture package still
withhold every global.

## Tests
`script_outside_tests.rs` (the plant, 11 forms, the 12 plants of audit 2, quiet files, files that
are not read, the cited places, an unreadable file), `script_member_patch_tests.rs`;
`tests/test_collector_false_pass_ts_outside_writer.py` (the plant, the 10 audit forms, a hidden
folder, PASS under the printed assumption) and `tests/test_collector_false_pass_ts_member_patch.py`.
