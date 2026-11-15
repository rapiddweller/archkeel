# AD-281 Retire unused tooling

**Status.** Accepted. The owner approved the list on 2026-10-30.

**Decision.** Remove repository tooling that no gate, workflow or user reads. The Git history is
the archive: restore a file from it when a real need comes back.
1. Rule yield: `tools/rule_yield.py`, its docs and its evidence files. AD-140 is retired.
2. GitHub order receipts: `tools/github_pr_report.py`, the two initial-PR receipt workflows and
   the report-only CI job. AD-141 is retired. AD-143 loses its receipt producer. The ordering
   check in `src` is gone with the Python code (AD-432).
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

**Amended (#767).** The result schemas `command-result.schema.json`, `command-result-12.0` and
`command-result-13.0` no longer define the host source `github_initial_pr_head`, its provenance
condition, the member `initial_pr` and `$defs/initialPR`. No producer or reader remains in `src`,
`native` or the tests. Both versioned files are unreleased: no tag holds them.

**Checks.** `tests/test_make_gate.py` pins the four workflow files. `git grep -n initialPR` finds
no schema.
