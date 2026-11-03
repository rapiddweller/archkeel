# AD-285 `archkeel explore` shows the code as it is, with no contract

**Status.** Accepted. Issues #791 and #687, epic #783.

**Decision.**
1. `archkeel explore [--root PATH] [--output DIR] [--json]` needs no ArchKeel file and no setup.
2. Scope: the `init` options `--language`, `--source`, `--namespace`, `--tsconfig` (one
   definition), else `init` detection (AD-47) of one Python package; TS and Dart need options.
3. Grouping: a temporary contract `archkeel-explore-layout.json` outside the repository has one
   component for each top-level child (the `init` grouping); its provenance is that file. It has
   no rule, `public`, `requires` or decision. The collector runs once for both passes.
4. Output: `architecture.json` and the report pages go to `DIR`, else to
   `$XDG_CACHE_HOME/archkeel/explore/<root_digest>/` (default `~/.cache`). An output inside the
   root exits 2. Each run observes again and first removes its old files.
5. No rule, no verdict: a valid observation with no declared rule and no UML target gives
   `target: unavailable` and `declared_rules: UNKNOWN`, also in `report --input`. An invalid
   contract shows its diagnostics only. `validate` keeps PASS: it says the contract is valid and
   that no rule was checked. The result is a `report` result.
6. Identity: `source.git_head`, `source.dirty`, `source.source_digest` (worktree content),
   `analyzer.version`, `analyzer.code_digest`; the result adds `root_name` (basename) and
   `root_digest` (sha256 of the resolved root, 16 hex), never the absolute path.
7. In this mode one line comes first: counts, the 8 largest components with their module
   counts, and the `__main__` modules. A closed table adds edges and names other components
   import ("N more" for the rest); the findings start closed, so the Explorer fits at 800x600.
   This amends AD-264 and AD-258 for this mode only.
8. Exit 0: complete. Exit 2: no scope, no Git commit, output inside the root, incomplete coverage.

**Graph for a view check.** `architecture_report(parse_observation(...))`: `observed` has
entities (stable `id` such as `MOD-`, `SYM-`; a `kind`) and relationships (`kind` such as
`imports` or `calls`, `source_id` to `target_id`, `resolution`, `evidence_ids`); `memberships`
map each `COMP-` id to its `MOD-` ids.

**Reason.** `report` without `archkeel.toml` exits 2 and asks for `init`, which writes a draft.
A newcomer must see what is there first. A contract with no rule decides nothing.

**Rejected.** A second renderer or a server. An implicit `init` or a contract file in the
repository. Components from a file walk (a second collector). A mark by contract file name.

**Limits.**
- `root_name` and `root_digest` are in the result, not in `architecture.json` (an exact header).
- `--only architecture` gives `UNKNOWN` without `target`: its published schema is byte-exact.
- Imports are not calls or a runtime order; an unresolved call stays a coverage gap. Entry points
  are `__main__` modules only. Git can refresh its index file in a run.

**Checks.** `tests/test_explore.py` and the demo row `explore-contract-free`.
