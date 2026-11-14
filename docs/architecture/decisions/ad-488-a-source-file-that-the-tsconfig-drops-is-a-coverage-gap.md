# AD-488 A source file that the TSConfig drops is a coverage gap

**Status.** Proposed. Part of #880. It closes a false PASS of release 4.0.1 and of the core.

**Problem.** The TypeScript collector reads the files that the TSConfig selects (`files`,
`include`, `exclude`, `allowJs`, `extends`) inside the scan roots (`config.rs::load_config`).
A file under the scan roots that the TSConfig drops was never discovered. So the reply showed
`files_discovered == files_read == files_parsed`, the scope proof found a complete scope, and an
import in the dropped file was invisible. A `complete_requires` rule gave PASS with an undeclared
edge. Release 4.0.1 gives the same PASS (exit 0) for each of the eight forms below.

**Decision.**
1. After the collection, the collector lists the project source under the scan roots without the
   TSConfig (`native/typescript/src/unselected.rs`). Project source is each file with a
   TypeScript, declaration or JavaScript suffix, also in a dot directory and also a `.min.js`.
2. These files are not project source:
   - a file under `node_modules`, `bower_components` or `jspm_packages`;
   - a file under the `outDir` or `declarationDir` of the TSConfig, unless that directory holds a
     scan root;
   - a file that a source of the same stem shadows (`a.js` or `a.d.ts` beside `a.ts`): the
     compiler writes it when no `outDir` is set;
   - a test source that a request with `exclude_test_sources = true` removes (AD-313).
3. Each project source file that the collection did not read is one collection gap with the
   module of the file: "Source file under the scan roots is not selected by the TSConfig: <path>".
4. The gap is not a pair gap, so the coverage of the reply is incomplete (`Incomplete::CoverageGaps`)
   and no rule of the run can PASS. A dropped file that a selected file imports is still read, so
   its imports can FAIL a rule.
5. `references` keeps its existing gap: "Project references require separately observed projects".

**Forms (tests).** `exclude`, a narrow `include`, `files`, `exclude` through `extends`, a
`*.test.ts` pattern, a `.d.ts` pattern, JavaScript with `allowJs` off, and a dot directory that the
default `include` skips: each is a named gap, UNKNOWN, exit 2. Controls that keep PASS: an installed
package, an `outDir`, emitted files beside their source, and the request test exclusion.

**Measurement.** `fixtures/matrix.json`: only `L-nest-realworld` changes, from 68 to 71 gaps (three
`*.spec.ts` files under `src/` that its TSConfig excludes); its six rules were UNKNOWN before.
`H-typescript` stays 9 PASS and 1 UNKNOWN. Of the 147 TypeScript corpus cases, one case gets a gap:
`s4/a-test-file-without-the-exclusion-passes`, whose excluded test file imports the undeclared
package `left-pad`. That is the same false PASS, and no test pinned its verdict.

**Limits.** The gap makes the whole run UNKNOWN, also for a rule whose scope does not hold the
file. A gap scoped to the rules that read the module needs a model change; it is not in this record.
The collector reads one TSConfig: a second TSConfig in the tree selects nothing, so its files are
gaps unless the configured TSConfig selects them. A gitignored source under the scan roots is
project source.

**Rejected.** Read a dropped file for its imports anyway: it adds modules that the compiler does
not see and changes the module rules. Skip dot directories and `.min.js`: a silent limit.
Keep 4.0.1 behaviour: a silent false PASS.

**Tests.** `tests/test_cli_core_ts_config_dropped.py` (eight forms, `references`, four controls, a
dropped file that a selected file imports), `native/typescript/src/unselected_tests.rs`, the
`L-nest-realworld` golden reply and `fixtures/matrix.json`.
