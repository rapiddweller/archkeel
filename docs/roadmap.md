# Roadmap

This file is the single roadmap for implemented and planned Archkeel work. A feature is done
only when its row names repository evidence.

## Done

| Capability | Evidence |
|---|---|
| `report`, `check`, three independent verdicts and exit codes 0/1/2 | `bff87f4`; `tests/test_cli.py`; `tests/test_check_diagnostics.py` |
| Regression checks compare raw counts and ratios with integer cross-multiplication | Fixture A; `tests/test_ratchets.py`; `make demo` |
| Precommitment order M → B → E → H from host records | Fixture B; `tests/test_ordering.py`; `make demo` |
| A declared and fulfilled change passes | Fixture C; `make demo` |
| Exit 2 carries diagnostics and invalid locks never become empty state | `tests/test_check_diagnostics.py`; `tests/test_report_diagnostics.py` |
| D-self checks Archkeel's own contract | `tests/test_self.py`; `fixtures/D-self/`; `make check` |
| Old analyzer runtimes produce `runtime_mismatch` instead of misleading parse errors | `fixtures/E-runtime/`; `tests/test_runtime_delta.py` |
| Unresolved calls have a reproducible classifier and documented limits | `25c8f3f`; `19236c2`; `tools/classify_unresolved.py`; `docs/known-limits.md` |
| Regression checks were replayed on real Repo #2 and EE histories | `5f3dfa6`; `cde4d7c`; `docs/evidence/5d-ee-replay.json` |
| Repository hygiene enforces local-path and Python-header rules | `f5aaca3`; `tests/test_repository_hygiene.py` |
| The Python analyzer is bundled and independent of DataMimic EE | `24d5d97`; `tests/test_analyzer.py` |
| `report` produces a styled HTML evidence report | `d7d3eb5`; `c47745d`; `tests/test_html_report.py` |
| Release 0.1.0 is published on PyPI | tag `0.1.0` at `e0a1c93`; [PyPI release](https://pypi.org/project/archkeel/0.1.0/) |
| GitHub CI checks source and distributions | `.github/workflows/ci.yml`; run `34835083322` at `2fa6ffd` |
| `make demo` reproduces cases A, B and C | `ed0faba`; `tests/test_demo.py` |
| Rendering is isolated from the deterministic core | `f2cbeb8`; `architecture-contract.json` |
| The core receives analyzer and host adapters from the CLI | `53a0d22`; `tests/test_self.py` |
| The analyzer package and active architecture documentation use one name | `2fa6ffd`; `tests/test_analyzer.py` |
| The component contract is closed and its graph matches observed imports | `tests/test_self.py`; `docs/architecture/archkeel.md`; `make check` |
| PASS, FAIL and NOT CHECKED check results have distinct HTML evidence | `tests/test_html_report.py`; `tests/test_demo.py`; `make demo` |
| Contract 2.0 has one typed model, JSON Schema and deterministic validation | `schema/architecture-contract.schema.json`; `tests/test_contract_model.py`; `tests/test_validation.py` |
| All class-A rule types are enforced with one violation probe each and applied to Archkeel | `docs/rules.md`; `tests/test_analyzer.py`; `architecture-contract.json` |
| Terminals get a Rich summary with real `--help`; pipes and `--json` keep JSON | `376a3ab`; `tests/test_cli.py`; `tests/test_terminal.py` |
| `init` drafts a closed contract that reproduces Archkeel's own component rules | `fe5214a`; `tests/test_onboarding.py`; `docs/onboarding.md` |
| `skill install claude\|codex` writes one packaged agent instruction source | `99f5743`; `tests/test_skill.py` |
| Fixture A leads the README with its report and terminal view | `make demo-screenshots`; `docs/assets/` |
| CI validates Archkeel's contract and uploads its self-observation | `.github/workflows/ci.yml` |
| Release 0.2.0 is published on PyPI | tag `0.2.0` at `07a2df6`; release run `34881396333`; [PyPI release](https://pypi.org/project/archkeel/0.2.0/) |
| Analyzer records share one typed envelope; `Any` annotations fell from 118 to 35 | `ac547bc`; `analyzer/embedded/records.py`; `fixtures/D-self/` |
| Architecture decisions AD-1 to AD-6 are recorded. AD-1, AD-2, AD-4, AD-5 and AD-6 have tests or type checks; AD-3 comparability is enforced by digest, and its version label is reviewed by hand. Long functions fell from 20 to 16, each with a named reason | `docs/architecture/decisions/ad-01-analyzer-modules-are-flat-and-singlepurpose.md`; `docs/architecture/decisions/ad-02-json-has-one-type.md`; `docs/architecture/decisions/ad-03-the-analyzer-digest-decides-comparability-the-version-names.md`; `docs/architecture/decisions/ad-04-module-length-alone-does-not-justify-a-split.md`; `docs/architecture/decisions/ad-05-invariants-live-where-values-are-built.md`; `docs/architecture/decisions/ad-06-a-function-has-one-responsibility.md`; `bb5c401`; `dc28681`; `04344b6`; `67b8b62`; `13c61c1`; `tests/test_analyzer.py`; `tests/test_repository_hygiene.py` |
| Report bytes are measured as independent of hash seed, clone path, working directory, time zone and locale (AD-7) | `f392702`; `tests/test_determinism.py`; CI run `34921160319` |
| Class C judgments are defined, and `assert` and `broad_except` are Class A forbidden constructs with `allowed_sources`, applied to Archkeel (AD-8) | `0b61873`; `b5090ca`; `59fc6cf`; `docs/rules.md`; `architecture-contract.json` |
| Components declare `public` interfaces; `interface_boundary` enforces them, validation reports drift, `init` drafts them and the report shows component communication with signatures (AD-9) | `289e81f`; `0809021`; `05beddc`; `a2f2427`; `abb8f96`; `f87bc72`; `39c8917`; `docs/evidence/ad9-interface-profile.md` |
| A test rejects unquoted Mermaid labels that break the parser, and CI renders every Mermaid block with pinned mermaid-cli (AD-13) | `59a678b`; `tests/test_mermaid.py`; CI run `34937525824` |
| Every checkable item has a catalogued demo on the shop sample, with real `check` runs for regressions and the protocol, and validation diagnostics carry codes (AD-11, AD-12) | `60f9f4c`; `c46ba7c`; `docs/architecture-demo.md`; `tests/test_architecture_demo.py` |
| The report headline follows its verdicts instead of the exit code alone (AD-14) | `e383d62`; `tests/test_html_report.py`; `tests/test_terminal.py` |
| An internal 13-component service was onboarded by interview and, blind, in auto mode: 156 pair decisions each, first reports FAIL with 162 and 199 violations, 89.7% blind agreement; anonymized evidence and findings are published | `044afbc`; `docs/evidence/internal-service/` |
| An import that a forbidden dependency rejects counts once, not again as an interface violation (AD-18) | `f80bf72`; `8531bdb`; `tests/test_analyzer.py` |
| Printed reports keep fingerprints inside the page | `make demo`, then Chrome headless `--print-to-pdf` of cases A, B and C |
| The HTML report draws component flow: one width for every edge with its import sites written on it, violated edges with their rule ids, a legend and the heaviest connections (AD-10) | `b1fa8df`; `7b2502a`; `tests/test_flow.py`; `tests/test_html_report.py` |
| Onboarding is a decision interview: `allowed_dependency`, contract 2.1.0, `decision.open` and `decision.conflict`, open decisions with option rules, component-level enforcement (AD-15) | `1951aa0`; `4a8548b`; `540226c`; `4b5936e`; `0740030`; `919f514`; `tests/test_decisions.py`; `tests/test_onboarding.py` |
| Every rule records `decided_by`; the skill runs an interview or auto mode, and reports count agent decisions (AD-16) | `52be155`; `819981a`; `c7baf9c` |
| Archkeel's contract names its quality goals, `ir` holds pure derivations, and the `accept` placeholder is gone (AD-17) | `0212447`; `e7d5178` |
| Release 0.3.0 is published on PyPI | tag `0.3.0` at `47dcd7f`; release run `34986034441`; [PyPI release](https://pypi.org/project/archkeel/0.3.0/) |
| One `sibling_isolation` rule isolates a set of peers instead of n*(n-1) prohibitions, applied to the eight analyzer collectors (AD-25) | `docs/rules.md`; `tests/test_analyzer.py`; `architecture-contract.json`; `docs/architecture-demo.md` |
| A report whose contract still leaves pairs undecided reads FAIL and names them, instead of passing on an empty target (AD-23) | `src/archkeel/render/summary.py`; `tests/test_terminal.py` |
| `ir` derives modules, inner edges, fan-in, fan-out and unresolved calls per component and per package, and `report` shows them without gating on them (AD-21) | `src/archkeel/ir/structure.py`; `tests/test_structure.py`; `docs/architecture/decisions/ad-21-structure-measurements-are-derivations-never-gates.md` |
| The analyzer records non-call uses of a symbol, so a function handed to a table counts as used; a quality claim without its signal stays UNKNOWN (AD-26) | `src/archkeel/analyzer/embedded/references.py`; `src/archkeel/analyzer/embedded/resolve.py`; `tests/test_analyzer.py` |
| The first Class D claim names the symbols nothing references, with its exemptions and the unresolved-call share beside it, and reports UNKNOWN without its signal (AD-26) | `src/archkeel/ir/references.py`; `tests/test_references.py`; `docs/rules.md` |
| The flow view opens a component and draws its modules and the imports between them, observed and undecided, from the same observation and no contract field (AD-24) | `src/archkeel/render/flow.py`; `src/archkeel/render/assets/flow.js`; `tests/test_flow.py` |
| Two levels are tied together (AD-20): a component names the contract describing its inside, the report names an inside larger than its own level, and two checks hold both levels to one public surface and to the prohibitions above; Archkeel's own `check` declares three sub-components where `init` would have drafted twelve | `4195e43`; `2e951c0`; `0625af3`; `src/archkeel/check/architecture-contract.json` |
| A declared inside is recorded in the observation under a kind of its own, derived in `ir`, judged by the rule code that judges the level above, and drawn as a level of the flow view: opening `check` shows `entry`, `foundation` and `policy` with their crossings at 21, 6 and 2 import sites, beside the one module no sub-component owns (AD-34) | `34fb7dd`; `e366f1c`; `7d825f2`; `26e4ba4`; `9bc30af`; `src/archkeel/ir/levels.py`; `tests/test_levels.py` |
| Every review claim is counted where the command answers, not only where the page is opened: `report` and `validate` print the counts in the terminal and carry them under `claims` in `--json`, with `null` for a missing signal (AD-35) | `src/archkeel/ir/decisions.py`; `src/archkeel/render/summary.py`; `tests/test_terminal.py`; `docs/rules.md` |
| An inside's rules are recorded under the component holding them, its violations name them there instead of being dropped by the evidence trace, the pair derivations above stay untouched by them, and a `check` snapshot carries the inside contracts the lock was written over (AD-36) | `src/archkeel/analyzer/embedded/contract.py`; `src/archkeel/ir/codec.py`; `tests/test_snapshot.py`; `tests/test_analyzer.py` |
| `make demo-onboarding` replays the agent-driven creation of a contract on the shop sample in one real command per step: `init` drafts 5 components and 20 open decisions, `validate` refuses the draft, the decided contract passes, the report names `store` as larger than its level, `init` drafts its 4 sub-components and 12 more pairs, the architect settles them with 3 `requires` entries, and a later crossing inside that level is caught and named for it | `fixtures/reproduce_onboarding.py`; `tests/test_onboarding_demo.py`; `make demo-onboarding` |
| The shop sample demonstrates both levels end to end: `store` declares an inside of four sub-components crossing at 3, 2 and 2 import sites, both levels pass on the clean sample, and four catalogued variants produce the inner `complete_requires` violation, both AD-20 checks and the missing-contract diagnostic | `fixtures/F-architecture/shop/store/architecture-contract.json`; `docs/architecture-demo.md`; `fixtures/F-architecture/docs/architecture/shop.md` |
| A method call on a receiver whose type a literal or an annotation makes statically obvious resolves against a hand-written stdlib method table instead of counting as dynamic noise, only when every binding of the receiver's name agrees: classifying Archkeel's own unresolved calls falls from 703 of 3,982 (17.65%) to 421 of 4,051 (10.39%) on a live re-scan (AD-37) | `src/archkeel/analyzer/embedded/receiver_types.py`; `src/archkeel/analyzer/embedded/resolve.py`; `src/archkeel/analyzer/embedded/calls.py`; `tests/test_analyzer.py` |
| A call result is typed from a closed table of documented library types, a constructor the import binding names or a method whose documented return is in the table, and claims only `partially_resolved`: Archkeel's own unresolved calls fall from 421 of 4,071 (10.34%) to 381 of 4,101 (9.29%) (AD-40) | `src/archkeel/analyzer/embedded/receiver_types.py`; `src/archkeel/analyzer/embedded/resolve.py`; `tests/test_analyzer.py` |
| Where `Any` may appear is the contract's `CONSTRUCT-NO-ANY` rule with AD-2's two owners as `allowed_sources`, no longer a grep in a test (AD-41) | `architecture-contract.json`; `tests/test_source_types.py` |
| A `requires` entry may name the modules it goes `through`; `complete_requires` covers only those, and the analyzer's twelve `DEP-ANALYZER-NO-IR-*` prohibitions became one permission through `ir.model` and `ir.codec`, 26 rules to 14 (AD-42) | `src/archkeel/analyzer/embedded/violations.py`; `src/archkeel/ir/model.py`; `architecture-contract.json`; `tests/test_analyzer.py` |
| A drafted component carries the size `structure_metrics` already measures instead of a bare name: the generated table gains Modules and Inner edges columns, `init --json` gains `draft_sizes`, and the terminal names the drafted component whose module count uniquely leads, or that none does (AD-38) | `src/archkeel/ir/structure.py`; `src/archkeel/check/onboarding.py`; `tests/test_onboarding.py`; `tests/test_terminal.py` |
| An empty `selected_changes` is a legal E declaration for a candidate with no semantic change; under it `check` fails on any semantic change in any of the eight delta dimensions, not only the six guardrail ones (AD-39) | `src/archkeel/check/expectation.py`; `tests/test_expectation.py`; `fixtures/demo_catalog_check.py::protocol-empty-declaration`; `docs/architecture-demo.md` |
| The five per-counter `coverage` counters stopped being declarable `semantic_changes`, and `from __future__ import annotations` stopped counting as an `api_crossings` entry: adding `src/archkeel/ir/labels.py` now declares 1 entry instead of 7 (AD-43) | `src/archkeel/check/delta.py`; `src/archkeel/check/python_profile.py`; `tests/test_delta.py::test_one_module_with_one_intra_component_import_is_one_semantic_change` |
| `dependency_edges` joined the fixed guardrail dimensions: an `added` entry a non-empty declaration never named is a guardrail failure, named by dimension, kind and fingerprint, closing the AD-39 Limit (AD-44) | `src/archkeel/check/expectation.py`; `tests/test_expectation.py`; `fixtures/demo_catalog_check.py`; `fixtures/demo_catalog_check_regressions.py` |
| `analyzer` declares an inside too, not only `check`: `orchestration`, `collectors` and `foundation`, the ten collectors matching `COLLECTORS-ISOLATED` unchanged, both levels passing with zero violations on the current source (AD-45) | `src/archkeel/analyzer/architecture-contract.json`; `architecture-contract.json`; `tests/test_self.py` |
| After a contract edit, `validate --write-graph` rewrites only the edges of the one marked component graph from the observed imports, sorted as `init` writes them and keeping the page's own diagram line; a block with a `subgraph`, a labeled edge or a style is left to a hand edit the remedy names; `graph.drift` names the command, and Archkeel's own graph was regenerated with it (AD-46) | `src/archkeel/check/validation.py`; `src/archkeel/cli/__init__.py`; `tests/test_cli.py::test_validate_write_graph_regenerates_only_the_marked_graph`; `tests/test_validation.py` |
| `init` scans the top-level package `pyproject.toml`'s `[project] name` names when a test package sits beside it, and still exits 2 with `scope_empty` when no package or several match: a copy of `datamimic_ce` (`datamimic_ce/` beside `tests_ce/`) now drafts with exit 0 where it stopped with exit 2 (AD-47) | `src/archkeel/check/onboarding.py`; `tests/test_onboarding.py` |
| `forbidden_construct` covers the write side of reflection, `setattr`, `delattr`, `vars` and `x.__dict__`, and `string_literal_compare`: a `==`/`!=` with a `str` literal, a membership test in a literal of them or a `match` on one, wherever it stands, excluding `__name__ == "__main__"`. Archkeel forbids the four reflection constructs with zero hits; its own 181 hits in 37 of 62 modules keep `string_literal_compare` off its contract (AD-48) | `src/archkeel/analyzer/embedded/constructs.py`; `tests/test_analyzer.py`; `fixtures/demo_catalog_constructs.py`; `architecture-contract.json` |
| An allowance may name its module exactly: `external_dependency_scope` and `forbidden_construct` take `exact_sources` beside the `allowed_sources` prefixes, so a package root is scoped on its own, Archkeel's own contract narrows four of its five prefix allowances, `rich_argparse` from the `archkeel.cli` package to its root module, and both rule kinds record every exemption they grant (AD-49) | `src/archkeel/analyzer/embedded/violations.py`; `src/archkeel/analyzer/embedded/contract.py`; `src/archkeel/ir/codec.py`; `schema/architecture-contract.schema.json`; `architecture-contract.json`; `tests/test_analyzer.py`; `tests/test_validation.py` |
| The shop sample demonstrates `exact_sources` and both `graph.drift` remedies: `CONSTRUCT-NO-BROAD-EXCEPT` exempts exactly `shop.cli.main.main`, twin rows run one nested handler under the exact and the prefix list (reported, allowed), a renamed component leaves a stale page whose remedy names `validate --write-graph`, and a page with a `subgraph` is left to a hand edit (AD-49, AD-46) | `fixtures/demo_catalog_constructs.py`; `fixtures/demo_catalog_validation.py`; `tests/test_architecture_demo.py`; `docs/architecture-demo.md` |
| A `requires` entry and a component record `decided_by`, the component's covering its `public` list and defaulting its entries, and `agent_decisions` counts a rule, an edge and a declared interface alike: Archkeel's own three contracts attribute all twelve components to the architect, and `validate` reports `[0, 41]` where it reported 16 rules (AD-50) | `src/archkeel/ir/model.py`; `src/archkeel/ir/codec.py`; `src/archkeel/ir/decisions.py`; `src/archkeel/analyzer/embedded/contract.py`; `src/archkeel/check/onboarding.py`; `schema/architecture-contract.schema.json`; `architecture-contract.json`; `tests/test_decisions.py`; `tests/test_analyzer.py` |
| A result carries its violations grouped by rule and by crossed component pair: `report --json` and `validate --json` add `violations_by_rule` and `violations_by_component_pair`, derived once from the records the result already reports, so a refactoring can be measured per change without decoding `architecture.json` (AD-51) | `src/archkeel/ir/decisions.py`; `src/archkeel/ir/model.py`; `src/archkeel/check/report.py`; `src/archkeel/check/validation.py`; `tests/test_decisions.py` |
| A violation is named by its rules and sorted subjects, not its position, so an edit above a violating line no longer renames it; `validate --baseline <file>` fails only on a violation the file does not state and on one it states that nobody violates any more (exit 1 through `failures`), `--write-baseline` writes the file, and `validate` without it is unchanged (AD-52) | `src/archkeel/ir/baseline.py`; `src/archkeel/ir/codec.py`; `src/archkeel/check/validation.py`; `src/archkeel/cli/__init__.py`; `schema/violation-baseline.schema.json`; `tests/test_baseline.py`; `tests/test_cli.py::test_validate_baseline_writes_then_gates_on_new_violations` |
| The sdist's `only-include` carries `src`, `schema` and `README.md`, what rebuilds the wheel, and never a test suite a tarball cannot run: a fresh `uv build` of the unpacked sdist reproduces a working wheel, and a test asserts every listed path exists and none of them is `tests`, `fixtures` or `tools` | `pyproject.toml`; `tests/test_repository_hygiene.py::test_sdist_ships_library_and_build_inputs_only`; `docs/reference.md` |
| `from pkg import name` follows `pkg/__init__.py`'s own top-level binding before a same-named submodule, computed once up front and read out for the plain `from . import name` re-export idiom, which still binds the submodule: `shop.store`'s own `sqlite` attribute now makes `shop.app`'s crossing an `INTERFACE-BOUNDARY` violation instead of the wrong `DEP-APP-NO-STORE-SQLITE` forbidden-dependency finding on a submodule the code never touches (AD-53) | `src/archkeel/analyzer/embedded/imports.py`; `tests/test_analyzer.py`; `fixtures/demo_catalog_interfaces.py`; `docs/architecture-demo.md` |
| `ir.baseline.violation_rows` types one `ViolationRow` per violation record - fingerprint, both modules, symbol, both components, evidence ids - and `ir.codec.load_observation(path)` is the one supported call from a file on disk; `observed_violations` (AD-52) and `violation_counts` (AD-51) now build on the same rows instead of their own loops, and `parse_record` rejects an untrusted VIOLATION record with no rule id instead of letting a count index past it (AD-54) | `src/archkeel/ir/baseline.py`; `src/archkeel/ir/codec.py`; `src/archkeel/ir/decisions.py`; `docs/reference.md`; `tests/test_violations.py`; `tests/test_self.py::test_self_contract_public_matches_drafted_proposal` |
| `docs/architecture/archkeel.md`'s 53 decision records, AD-24a and AD-24b included, split one file per decision under `docs/architecture/decisions/`; the document keeps its title, `## Layers`, `## Allowed dependencies` and the marked component graph, and `## Decisions` becomes an index table in document order with cross-references turned into relative links (AD-55) | `docs/architecture/archkeel.md`; `docs/architecture/decisions/`; `tests/test_repository_hygiene.py::test_decision_index_matches_decision_files` |
## Next

1. Compare the self-observation of a pull request with `main` in CI, report-only. It needs an
   accepted baseline on `main`, which the M → B → E → H protocol does not provide for
   ordinary pull requests.
2. Title each validation panel with its own code instead of `contract_invalid`, and group the
   panels by code with a count, so a first run does not present fifteen identical-looking boxes
   (AD-19). Evidence: one `validate` run on the shop sample with a removed decision prints 15
   panels, all titled `contract_invalid`, covering graph drift, rule violations and the open
   decision.
3. Replace internal vocabulary in the HTML report labels: `Complete ArchitectureIR inventory`,
   `Canonical result`, `Reproduction metadata`, `Coverage dimension`, `Fingerprint` and
   `Publication order evidence` name concepts a reader has to look up (AD-19).
4. Show the analyzer, contract and checker digests in the check report heading, so a reader sees
   without the JSON that the two snapshots were comparable at all.
5. Group a sub-root draft by import connectivity rather than by directory. Evidence: on this
   repository `init --source src/archkeel/analyzer --namespace archkeel.analyzer` drafts 3
   components while `embedded` alone hides 18 of the scope's modules; `init` on
   `src/archkeel/ir` drafts 14 components and 182 open decisions; `init` on
   `src/archkeel/check` drafts 12 components and 132 open decisions where the architect
   settled on 3. Naming each draft's size (AD-38) makes the imbalance visible but does not fix
   it: a directory-per-component draft still proposes 12 or 14 components to consolidate by
   hand, one per module, regardless of how those modules import each other.
## Later

- Let a second level run on its own (AD-20): an inside is recorded, derived, judged, drawn and
  carried through `check` from the outer run (AD-34, AD-36), but it still has no `archkeel.toml`
  of its own, so `validate --root src/archkeel/check` cannot evaluate it as a level in its own
  right. Of its rules only `complete_requires` is evaluated, against the imports the outer scan
  collected; every other kind it declares is recorded and shown but never enforced, an
  `external_dependency_scope` in particular, which is also not compared against the level above.
  An inside contract's own provenance documents are not materialized for `check`, because no
  command reads them. One level down is recorded, so an inside declared within an inside is not
  drawn. Evidence: `init` on that scope drafts 12 sub-components and 132 open decisions, one
  component per module, where the three decided layers need 6.
- Make the analyzer a process port with a language profile and prove it with a second analyzer
  (AD-22). Six places still assume Python: the import in the CLI, the namespace pattern in the
  configuration, the `public` and dependency patterns in the schema, the construct enum and the
  runtime gate.
- Decide the regression policy, implement `accept`, add a GitHub host adapter and consider
  renaming the `ratchets` schema field to `regression_checks`. Evidence: `5a07aed` reduced
  `calls_unresolved` from 484 to 466 while `unresolved_ratio` worsened from 19.28% to 19.46%
  because well-resolved duplicate code was deleted; a ratio-only check would reject this
  improvement. `bbab17c` showed the opposite case for an absolute-only check.
- Act on the open onboarding findings in `docs/evidence/internal-service/README.md`: assign a
  package `__init__` exactly, check `requires-python` before scanning, and measure auto-mode
  agreement on a second repository.
- Split `ir/codec.py` along its contract, observation, delta, result and lock seams (AD-17).
- Add `propose` and `next`.
- Integrate Archkeel into DataMimic EE.
- Add digest-bound blind LLM review whose verdict remains a hypothesis.
- Track finding lifecycle states on existing fingerprints without changing check outcomes.
- Add a publication timeline when check results carry host-record timestamps.

## Excluded

- A total score as a gate.
- Empty state as a fallback.
- A claim for symbols referenced exactly once. Measured on Archkeel: 163 of 564 symbols are private
  and referenced once, and AD-6 produces them deliberately, because a function kept under 80 lines
  extracts helpers its only caller uses. Narrowing the claim to a reference from another module
  names none, since a private symbol reaching another module is already an `interface_boundary`
  violation. A claim that either repeats a verdict or names a quarter of the repository teaches
  readers to skip it, which AD-26 warns against.
