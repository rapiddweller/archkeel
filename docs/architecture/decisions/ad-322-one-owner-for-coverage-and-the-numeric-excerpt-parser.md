# AD-322 One owner for coverage and for the numeric excerpt parser

**Decision.** This is step S3 of issue #880. Two rules and one parser had several copies. Each now
has one owner.

1. **Is the observation complete?** `archkeel.ir.coverage.observation_complete` answers it. An
   observation is complete when its status is PASS and it records no failure.
2. **Do the scan roots contain the source?** `scan_covers_packages`, `scan_covers_exact_modules`,
   `scan_domains_complete` and `observation_covers_rule` answer it in the same module. They map
   each module to its physical directory and ask whether a scan root contains it. `under_roots`
   is the one test of a path against relative roots.
3. **The numeric excerpt parser.** `archkeel.ir.source_proofs.parse_numeric_evidence_excerpt`
   reads the one-line excerpt of an evidence as the statements that it starts. It adds a synthetic
   body, decorated function or `if` where one line has none.

`coverage` belongs to the `architecture` owner of AD-315. The epic named the `evidence` owner,
but `source_graph` is in `architecture` and needs the first rule, and `architecture` cannot
import `evidence`. The module imports only `model`, `facts` and `profiles`.

**Copies removed.**
- The text `coverage.status == Verdict.PASS` stood on 28 lines of `ir` and `check`, with the
  failures added on some of them. The 24 callers of `observation_complete` replace them.
- `decisions` and `check.evaluation.rules` each had a family that maps modules to directories:
  4 and 6 functions. The rules family moves to `coverage`. `decisions` and the rules call it.
- `analyzer.python.constructs` and `ir.facts_validation` each had the same 6 parser functions.
  Both call `source_proofs`. On 30 044 excerpts the old and the new parser give the same
  statements and the same offset.

**The copies disagreed. This decision chooses the rule.**
- *Failures.* Some callers called a PASS with failures complete (`source_graph`,
  `module_explore`, `report_projection`, `report_graph`, `duplication`, `check.delta`, one site
  in `view_spec` and two in `decisions`). Others did not (two sites in `view_spec`,
  `check.report`, `check.ratchets` and seven in `decisions`). A recorded failure is missing
  evidence, so the answer is not complete. The producer never writes that state:
  `check.evaluation.evaluate` sets FAIL when it records a failure. Only a saved observation that
  was written by hand can have a PASS with failures.
- *A module that is off its name layout.* The live scan did not cover such a scope, because the
  physical domain of the module is unknown. The saved-observation copy skipped the module and
  called the scope covered. The live scan is the rule, because evidence cannot prove a domain that
  it cannot place. This also covers a module in a folder of a different name. A saved observation
  with such a module now gives UNKNOWN where it gave PASS.
- *Absolute roots.* A root must be relative. An absolute root does not cover an absolute file
  path. The old copy in `decisions` said covered. Real collectors record relative paths.
- *A root that names the file itself.* The domain of a package is a directory. A root such as
  `src/pkg.py`, `src/pkg/__init__.py` or `src/a.ts` is not that directory, so it covers nothing.
  The old copy in `decisions` said covered.
- A recorded `root/**/*.py` is the same root as `root`. This is an input form, not a difference.
  `observation_covers_rule` reads it.

**Not changed.** `ObservationResult` in `model` checks that an incomplete observation has a
diagnostic. It reads the status only and stays. `DeltaCoverage` is another type. The excerpt
helpers `_selector_excerpt_replays`, `_call_evidence_nodes` and `_reference_excerpt_tree` replay
other rules; the last two call the parser. `facts_validation` loses its copy and gains one import.
This is the only change to a source-side file. `archkeel.api`, the saved formats and the `ir`
package name stay.

**Reason.** A rule with two spellings gives two answers on the first edge case. #882 pinned each
spelling and showed where they differ. A reader of the contract needs one answer.

**Result.** The same status for all 134 rules on `make self-validate`. The `validate` and
`explore` output is equal on the demo cases. The saved-format tests are the same. The amendment
`ad-322-coverage-amendment.json` binds the new public names in both contracts. It also binds the
one widening of a requirement: the analyzer may import `parse_numeric_evidence_excerpt` from `ir`.

**Check.** `tests/test_coverage.py` pins the owner, the rule for failures, for an unplaced module,
for absolute roots and for a root that names a file, and the absence of the old copies.
`tests/test_excerpt_parsers.py` pins the parser.
`tests/test_architecture_coverage_characterization.py` keeps the shared cases and the three
tests that kill the mutants `any` for `all`, an absolute root and the first exact module only.
