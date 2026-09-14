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

## Next

1. Add the deterministic framework: rule catalog, Contract 2.0.0, JSON Schema, `validate` and new rule types.
2. Add the Rich terminal view while preserving JSON for pipes and `--json`.
3. Add onboarding with `init` and agent skill installation.
4. Lead the README with the Fixture A failure report and document `make demo`.
5. Verify PASS, FAIL and UNVERIFIABLE output on desktop, mobile and print PDF.
6. Publish D-self artifacts and a report-only pull-request comparison in CI.
7. Prepare release 0.2.0 after explicit approval.

## Later

- Decide the regression policy, implement `accept`, add a GitHub host adapter and consider
  renaming the `ratchets` schema field to `regression_checks`. Evidence: `bbab17c` raised
  `calls_unresolved` from 474 to 479 while `unresolved_ratio` improved, so the absolute check
  would reject Archkeel's own commit.
- Add `propose`, `next` and an agent skill.
- Integrate Archkeel into DataMimic EE.
- Add an interactive review surface and navigable dependency graph.
- Add digest-bound blind LLM review whose verdict remains a hypothesis.
- Track finding lifecycle states on existing fingerprints without changing check outcomes.
- Add a publication timeline when check results carry host-record timestamps.

## Excluded

- A total score as a gate.
- Empty state as a fallback.
