# AD-285 `archkeel explore` shows the code as it is, with no contract

**Status.** Accepted. Issues #791 and #687, epic #783.

**Decision.**
1. `archkeel explore [--root PATH] [--output DIR] [--json]` needs no ArchKeel file and no setup.
2. Scope: the `init` options `--language`, `--source`, `--namespace`, `--tsconfig` (one
   definition), else `init` detection (AD-47) of one Python package; TS and Dart need options.
3. Grouping: a temporary contract `archkeel-explore-layout.json` outside the repository has one
   component for each top-level child (the `init` grouping); its provenance is that file. It has
   no rule, `public`, `requires` or decision. The collector runs once for both passes.
   Levels (Python): a component of more than 40 modules gets an `inside` contract in
   `archkeel-explore-levels/` with one child component for each direct subpackage, named after
   it; at most 4 levels. Its direct module files and one-module namespace subpackages stay its
   own; a child of 40 modules or fewer stays one leaf. Deterministic, no rule or `requires`.
   The heading names both counts, e.g. "7 top-level components (97 with all levels)".
4. Output: `architecture.json` and the report pages go to `DIR`, else to
   `$XDG_CACHE_HOME/archkeel/explore/<root_digest>/` (default `~/.cache`). An output inside the
   root exits 2. After the scope and HEAD checks, it removes only its own earlier files. Git runs
   with `GIT_OPTIONAL_LOCKS=0`, so `git status` does not rewrite the index: `.git` stays as it is.
5. Nothing declared, no verdict: a valid observation whose contract declares no rule, UML target
   or component intent (`responsibilities`, `public`, `requires`, ...) gives `target:
   unavailable` and `declared_rules: UNKNOWN`, also in `report --input`; a view check reads its
   groups as `unknown`. An invalid contract shows its diagnostics only. `validate` keeps PASS
   and says that no rule was checked. No role marker: published schemas fix the role enum.
6. Identity: `source.git_head`, `source.dirty`, `source.source_digest` (worktree content),
   `analyzer.version`, `analyzer.code_digest`; the result adds `root_name` (basename) and
   `root_digest` (sha256 of the resolved root, 16 hex), never the absolute path.
7. In this mode one line comes first (counts, the 8 largest components, `__main__` modules), then
   a closed table and closed findings, so the Explorer fits at 800x600. No level shows a
   deviation, Target or Diff. This amends AD-264 and AD-258 for this mode only.
8. Exit 0: complete. Exit 2: no scope, no Git commit, output inside the root, incomplete coverage.
9. Notes (explore only): on a complete scan that declares nothing, an undeclared or
   unreadable Python range (`runtime_mismatch`) goes to `notes` and shows as a coverage note.
   Any coverage failure keeps every diagnostic and exit 2, and so do a Python outside a declared
   range and an empty scope. `report` and `report --input` keep exit 2 for the range.

**Graph for a view check.** `architecture_report(parse_observation(...))`: `observed` entities
(`id` such as `MOD-`, `SYM-`; `kind`) and relationships (`kind`, `source_id` to `target_id`,
`resolution`, `evidence_ids`); `memberships` map each `COMP-` id to its `MOD-` ids.

**Reason.** A newcomer must see what is there before `init` writes a draft; no rule decides nothing.

**Rejected.** A second renderer or a server. An implicit `init` or a contract file in the
repository. Components from a file walk (a second collector). A mark by contract file name.

**Limits.**
- `root_name` and `root_digest` are in the result, not yet in `architecture.json` (exact header).
- `--only architecture` gives `UNKNOWN` without `target`: its published schema is byte-exact.
- The split threshold is the constant 40, with no option. A flat package of 200 or more
  modules stays one leaf.
- Imports are not calls or a runtime order; an unresolved call stays a coverage gap. Entry points
  are `__main__` modules only.

**Checks.** `tests/test_explore.py` and the demo row `explore-contract-free`.
