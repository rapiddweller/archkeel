# AD-281 Retire unused tooling

**Status.** Accepted. The owner approved the list on 2026-10-30.

**Decision.** Remove repository tooling that no gate, workflow or user reads. The Git history is
the archive: restore a file from it when a real need comes back.
1. Rule yield: `tools/rule_yield.py`, its docs and its evidence files. AD-140 is retired.
2. GitHub order receipts: `tools/github_pr_report.py`, the two initial-PR receipt workflows and
   the report-only CI job. AD-141 is retired. AD-143 loses its receipt producer; its ordering
   check in `src` stays until issue #767 removes `InitialPRHeadEvidence`.
3. TypeScript differential: the comparison with the frozen output of the old Node collector, its
   two reference files and its helpers `fixtures/typescript_scenarios.py` and
   `fixtures/typescript_realworld.py`. That collector is gone, so the reference cannot change.
   AD-210 no longer names the frozen adapter reference.
4. SVG figure tools: `tools/onboarding_svg.py`, `tools/terminal_svg.py` and two unused SVG files.
5. Dead maintenance tools: the artifact retention tool, the workflow registry tool, the
   unresolved-call classifier, the AD-9 interface profile tool and `maintenance.yml`. This
   replaces item 5 of AD-280. Four workflow files stay: CI, Full verification, Pages and release.
6. The committed plugin copy `plugins/archkeel/` and `make plugin-directory`. The repository root
   is the plugin; `make plugin-release` builds its ZIP. The icon moves to `docs/assets/`.

**Reason.** Nobody reads, lints or types this code. Rule yield had 800 lines and 1,184 test lines.

**Rejected.** Keep the tools outside CI: they still cost lint, type and test time. Move them to a
separate repository: nobody uses them.

**Limits.** Until issue #767, `src` accepts `InitialPRHeadEvidence`, but nothing here produces it.

**Checks.** `tests/test_make_gate.py` pins the four workflow files. `tests/test_initial_pr_check.py`
keeps the ordering check of `src`.
