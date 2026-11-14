# AD-488 A source file that the TSConfig drops is a coverage gap

**Status.** Proposed. Part of #880. It closes a false PASS of release 4.0.1 and of the core.

**Problem.** The TypeScript collector reads the files that the TSConfig selects (`files`,
`include`, `exclude`, `allowJs`, `extends`) inside the scan roots (`config.rs::load_config`).
A file under the scan roots that the TSConfig drops was never discovered. So the scope proof found a
complete scope, and an import in the dropped file could not fail a rule. Release 4.0.1 gives the
same PASS (exit 0).

**Decision.**
1. After the collection, the collector lists the project source under the scan roots without the
   TSConfig (`native/typescript/src/unselected.rs`): each file with a TypeScript, declaration or
   JavaScript suffix in any letter case, also in a dot directory and also a `.min.js`.
2. Each project source file that the collection did not read is one collection gap with its
   module: "Source file under the scan roots is not selected by the TSConfig: <path>". It is not a
   pair gap, so the coverage is incomplete and no rule of the run can PASS. A dropped file that a
   selected file imports is still read, so its imports can FAIL a rule.
3. A name or a directory is not a proof that a file is generated. A file beside its source (`a.js`,
   `a.jsx`, `a.d.ts`, `a.tsx` beside `a.ts`; `.mjs`/`.d.mts` beside `.mts`; `.cjs` beside `.cts`)
   and a file in the `outDir` or `declarationDir` are project source. A hand-written file can have
   each of these names, and `noEmit` writes nothing.
4. One exemption stays: an installed-package directory (`node_modules` or `jspm_packages` beside a
   `package.json`, `bower_components` beside a `bower.json`). Proof: a package manager writes this
   directory, and the project reaches its code only as an external package. The collector types
   such an import as an external target, and the external rules read it. The directory is project
   source again when the TSConfig selects a file in it, when a read import resolves to a local
   file in it, or when a `paths` target or `baseUrl` lies in it: an alias reaches code as source.
   A directory without its manifest is project source.
5. An exempt directory is skipped before the walk marks its real path as seen. So a link from an
   exempt name to project source does not hide the project source.
6. A test source that a request with `exclude_test_sources = true` removes is not a gap (AD-313).
7. `references` keeps its existing gap: "Project references require separately observed projects".

**Measurement.** `fixtures/matrix.json`: only `L-nest-realworld` changes, from 68 to 71 gaps (three
`*.spec.ts` under `src/` that its TSConfig excludes); its six rules were UNKNOWN before.
`H-typescript` stays 9 PASS and 1 UNKNOWN. Of the 147 TypeScript corpus cases, one case gets a gap:
`s4/a-test-file-without-the-exclusion-passes`, whose excluded test file imports the undeclared
package `left-pad`. The browser contract keeps its 881 gaps. The Studio UI contract gets one gap:
`src/archkeel/studio/ui/studio.js`, the checked-in bundle that its TSConfig does not select. The
bundle is code that no rule read, so its pin must name the gap.

**Limits.** The gap holds every rule of the run, not only the rules that read the file. A built
`dist` or emitted files under a scan root are gaps: narrow the scan roots to the source. Code in an
installed package that imports project source by a relative path is not read. The collector reads
one TSConfig. A gitignored source under the scan roots is project source.

**Rejected.** Exempt emitted names or build output directories: a name proves nothing. Read a
dropped file for its imports: it adds modules that the compiler does not see. Skip dot directories,
`.min.js` or upper-case suffixes: a silent limit. Keep 4.0.1 behaviour: a silent false PASS.

**Tests.** `tests/test_cli_core_ts_config_dropped.py` (eight forms, the 23 findings of the review of
#1160, `references`, two controls, a dropped file that a selected file imports),
`native/typescript/src/unselected_tests.rs`, the `L-nest-realworld` golden reply and
`fixtures/matrix.json`.
