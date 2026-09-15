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
| PASS, FAIL and UNVERIFIABLE check results have distinct HTML evidence | `tests/test_html_report.py`; `tests/test_demo.py`; `make demo` |
| Contract 2.0 has one typed model, JSON Schema and deterministic validation | `schema/architecture-contract.schema.json`; `tests/test_contract_model.py`; `tests/test_validation.py` |
| All class-A rule types are enforced with one violation probe each and applied to Archkeel | `docs/rules.md`; `tests/test_analyzer.py`; `architecture-contract.json` |
| Terminals get a Rich summary with real `--help`; pipes and `--json` keep JSON | `376a3ab`; `tests/test_cli.py`; `tests/test_terminal.py` |
| `init` drafts a closed contract that reproduces Archkeel's own component rules | `fe5214a`; `tests/test_onboarding.py`; `docs/onboarding.md` |
| Onboarding works on an internal 13-component service: 119 forbidden pairs, 121 rationale decisions, then `validate` exit 0 | Release-candidate wheel under Python 3.12, archived snapshot; not stored in this repository |
| `skill install claude\|codex` writes one packaged agent instruction source | `99f5743`; `tests/test_skill.py` |
| Fixture A leads the README with its report and terminal view | `make demo-screenshots`; `docs/assets/` |
| CI validates Archkeel's contract and uploads its self-observation | `.github/workflows/ci.yml` |
| Release 0.2.0 is published on PyPI | tag `0.2.0` at `07a2df6`; release run `34881396333`; [PyPI release](https://pypi.org/project/archkeel/0.2.0/) |
| Analyzer records share one typed envelope; `Any` annotations fell from 118 to 35 | `ac547bc`; `analyzer/embedded/records.py`; `fixtures/D-self/` |
| Architecture decisions AD-1 to AD-6 are recorded. AD-1, AD-2, AD-4, AD-5 and AD-6 have tests or type checks; AD-3 comparability is enforced by digest, and its version label is reviewed by hand. Long functions fell from 20 to 16, each with a named reason | `docs/architecture/archkeel.md`; `bb5c401`; `dc28681`; `04344b6`; `67b8b62`; `13c61c1`; `tests/test_analyzer.py`; `tests/test_repository_hygiene.py` |
| Printed reports keep fingerprints inside the page | `make demo`, then Chrome headless `--print-to-pdf` of cases A, B and C |

## Next

1. Compare the self-observation of a pull request with `main` in CI, report-only. It needs an
   accepted baseline on `main`, which the M → B → E → H protocol does not provide for
   ordinary pull requests.

## Later

- Decide the regression policy, implement `accept`, add a GitHub host adapter and consider
  renaming the `ratchets` schema field to `regression_checks`. Evidence: `5a07aed` reduced
  `calls_unresolved` from 484 to 466 while `unresolved_ratio` worsened from 19.28% to 19.46%
  because well-resolved duplicate code was deleted; a ratio-only check would reject this
  improvement. `bbab17c` showed the opposite case for an absolute-only check.
- Add `propose` and `next`.
- Integrate Archkeel into DataMimic EE.
- Add an interactive review surface and navigable dependency graph.
- Add digest-bound blind LLM review whose verdict remains a hypothesis.
- Track finding lifecycle states on existing fingerprints without changing check outcomes.
- Add a publication timeline when check results carry host-record timestamps.

## Excluded

- A total score as a gate.
- Empty state as a fallback.
