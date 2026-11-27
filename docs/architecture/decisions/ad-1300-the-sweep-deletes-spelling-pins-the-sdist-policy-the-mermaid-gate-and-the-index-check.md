# AD-1300 The sweep deletes spelling pins, the sdist policy, the mermaid gate and the index check

**Status.** Accepted. Owner order of 2026-11-27: purge every drift gate that is not ArchKeel itself (sweep groups 14 to 19). Amends AD-55, AD-752 and AD-1251.

**Decision.** Deleted:
1. Spelling and order pins of workflows, Make recipes and hooks: the flag lists of the native lint recipe, the
   SHA-format scanner of action pins, the copied platform tag list, the text of the build hook.
2. The source-level sdist include-list test (`test_repository_hygiene.py`) and its step in `tools/pr_report.py`.
3. `make mermaid`, `tools/mermaid_blocks.py`, `tests/test_mermaid.py`, the CI job `mermaid` and the Full step.
   GitHub renders the diagrams of the documents itself. The Mermaid blocks that the product reads
   (`archkeel-component-graph`) stay in the tests of the product.
4. The AST ban on literal timeouts of 15 or 30 seconds in `tests/test_timeout_support.py`.
5. The CONTRIBUTING lines that prescribe the contract sort, the tested 70-line limit and the closed set of shell modules.
6. `tools/decision_index.py --check`, `tests/test_decision_index.py` and the README claim that CI runs it. The listing stays.

**Kept.** Executed routing (which crates lint, which areas run), the selected-area check, the fail-closed aggregates, the
release and install runs, the executed decision step of Pages and `run_bounded`.

**Protects -> still covered by -> or none.**
| Removed | Still covered by |
|---|---|
| Flag and order spelling of recipes | the run of the recipe |
| SHA-format scanner | none (owner decision); review of the workflow diff |
| Platform tag list copy | the release and wheel tests that build each tag |
| Build hook text | the clean install test of the wheel |
| sdist include-list policy | the real sdist build and install (`make sdist smoke`) |
| Mermaid label parser and render gate | none (owner decision); GitHub renders the documents |
| Literal timeout ban | none (owner decision) |
| Decision number and heading check | none (owner decision); a shared number shows in the listing |

**Tests.** `tests/test_native_touched.py`, `tests/test_cli_native_core_scan.py`, `tests/test_publish_release.py`,
`tests/test_timeout_support.py`, `tests/test_pr_report.py`.
