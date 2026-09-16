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
| Architecture decisions AD-1 to AD-6 are recorded. AD-1, AD-2, AD-4, AD-5 and AD-6 have tests or type checks; AD-3 comparability is enforced by digest, and its version label is reviewed by hand. Long functions fell from 20 to 16, each with a named reason | `docs/architecture/archkeel.md`; `bb5c401`; `dc28681`; `04344b6`; `67b8b62`; `13c61c1`; `tests/test_analyzer.py`; `tests/test_repository_hygiene.py` |
| Report bytes are measured as independent of hash seed, clone path, working directory, time zone and locale (AD-7) | `f392702`; `tests/test_determinism.py`; CI run `34921160319` |
| Class C judgments are defined, and `assert` and `broad_except` are Class A forbidden constructs with `allowed_sources`, applied to Archkeel (AD-8) | `0b61873`; `b5090ca`; `59fc6cf`; `docs/rules.md`; `architecture-contract.json` |
| Components declare `public` interfaces; `interface_boundary` enforces them, validation reports drift, `init` drafts them and the report shows component communication with signatures (AD-9) | `289e81f`; `0809021`; `05beddc`; `a2f2427`; `abb8f96`; `f87bc72`; `39c8917`; `docs/evidence/ad9-interface-profile.md` |
| A test rejects unquoted Mermaid labels that break the parser, and CI renders every Mermaid block with pinned mermaid-cli (AD-13) | `59a678b`; `tests/test_mermaid.py`; CI run `34937525824` |
| Every checkable item has a catalogued demo on the shop sample, with real `check` runs for regressions and the protocol, and validation diagnostics carry codes (AD-11, AD-12) | `60f9f4c`; `c46ba7c`; `docs/architecture-demo.md`; `tests/test_architecture_demo.py` |
| The report headline follows its verdicts instead of the exit code alone (AD-14) | `e383d62`; `tests/test_html_report.py`; `tests/test_terminal.py` |
| An internal 13-component service was onboarded by interview and, blind, in auto mode: 156 pair decisions each, first reports FAIL with 162 and 199 violations, 89.7% blind agreement; anonymized evidence and findings are published | `044afbc`; `docs/evidence/internal-service/` |
| An import that a forbidden dependency rejects counts once, not again as an interface violation (AD-18) | `f80bf72`; `8531bdb`; `tests/test_analyzer.py` |
| Printed reports keep fingerprints inside the page | `make demo`, then Chrome headless `--print-to-pdf` of cases A, B and C |
| The HTML report draws component flow: edges weighted by import sites, violated edges with their rule ids, a legend and the heaviest connections (AD-10) | `b1fa8df`; `7b2502a`; `tests/test_flow.py`; `tests/test_html_report.py` |
| Onboarding is a decision interview: `allowed_dependency`, contract 2.1.0, `decision.open` and `decision.conflict`, open decisions with option rules, component-level enforcement (AD-15) | `1951aa0`; `4a8548b`; `540226c`; `4b5936e`; `0740030`; `919f514`; `tests/test_decisions.py`; `tests/test_onboarding.py` |
| Every rule records `decided_by`; the skill runs an interview or auto mode, and reports count agent decisions (AD-16) | `52be155`; `819981a`; `c7baf9c` |
| Archkeel's contract names its quality goals, `ir` holds pure derivations, and the `accept` placeholder is gone (AD-17) | `0212447`; `e7d5178` |
| Release 0.3.0 is published on PyPI | tag `0.3.0` at `47dcd7f`; release run `34986034441`; [PyPI release](https://pypi.org/project/archkeel/0.3.0/) |
| One `sibling_isolation` rule isolates a set of peers instead of n*(n-1) prohibitions, applied to the eight analyzer collectors (AD-25) | `docs/rules.md`; `tests/test_analyzer.py`; `architecture-contract.json`; `docs/architecture-demo.md` |
| A report whose contract still leaves pairs undecided reads FAIL and names them, instead of passing on an empty target (AD-23) | `src/archkeel/render/summary.py`; `tests/test_terminal.py` |
| `ir` derives modules, inner edges, fan-in, fan-out and unresolved calls per component and per package, and `report` shows them without gating on them (AD-21) | `src/archkeel/ir/structure.py`; `tests/test_structure.py`; `docs/architecture/archkeel.md` |

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
4. Open a component in the flow view and draw its modules and their imports from the same
   observation (AD-24). Evidence: 74 of the 142 observed module edges lie inside one component and
   are never shown.
5. Show the analyzer, contract and checker digests in the check report heading, so a reader sees
   without the JSON that the two snapshots were comparable at all.

## Later

- Tie two levels together (AD-20): a contract field that names the contract describing a
  component's inside, the measured number reported upward, and the two checks that both levels
  declare the same `public` interface and that nothing inside imports what the level above forbids.
  Evidence: a second level on `src/archkeel/check` drafted 12 sub-components and 132 open decisions
  with today's commands and no model change.
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
  package `__init__` exactly, regenerate the marked graph after a component cut, check
  `requires-python` before scanning, and measure auto-mode agreement on a second repository.
- Split `ir/codec.py` along its contract, observation, delta, result and lock seams (AD-17).
- Add `propose` and `next`.
- Integrate Archkeel into DataMimic EE.
- Add digest-bound blind LLM review whose verdict remains a hypothesis.
- Track finding lifecycle states on existing fingerprints without changing check outcomes.
- Add a publication timeline when check results carry host-record timestamps.

## Excluded

- A total score as a gate.
- Empty state as a fallback.
