# AD-285 `archkeel explore` shows the code as it is, with no contract

**Status.** Accepted. Issues #791 and #687, epic #783.

**Decision.**
1. `archkeel explore [--root PATH] [--output DIR] [--json]` needs no ArchKeel file and no setup.
2. Scope: the `init` detection (AD-47) finds the one top-level Python package. A mixed
   repository gives its Python package only; `scan_roots` names what was read.
3. Grouping: a temporary contract `archkeel-explore-layout.json` outside the repository has one
   component for each top-level child of the package (the `init` grouping). It has no rule,
   `public`, `requires` or decision. The collector runs once for both passes.
4. Output: `architecture.json` and the report pages go to `DIR`, else to
   `$XDG_CACHE_HOME/archkeel/explore/<root hash>/` (default `~/.cache`). An output inside the
   root exits 2. Each run observes again and first removes its old files.
5. No rule, no verdict: an observation with no declared rule and no UML target gives
   `target: unavailable` and `declared_rules: UNKNOWN`, also in `report --input`. Observed facts
   (findings, cycles, coverage) stay. The result is a `report` result with the optional `target`.
6. Snapshot identity: `source.git_head`, `source.dirty`, `source.source_digest` (worktree
   content), `analyzer.version` and `analyzer.code_digest`; the root is the cache key.
7. In this mode an inventory panel comes above the findings: the 8 largest components (modules,
   edges inside, incoming, outgoing), their `__main__` modules and the count of names other
   components import from them. This amends AD-264 for this mode only.
8. Exit 0: complete. Exit 2: no single Python package, no Git commit, output inside the root, or
   incomplete coverage; the diagnostic names the reason.

**Graph for a view check.** `architecture_report(parse_observation(...))`: `observed` has
entities with a stable `id` (`MOD-`, `SYM-`, ...) and a `kind`, and relationships with a `kind`
(`imports`, `calls`, `references`, ...), `source_id` to `target_id`, a `resolution` and
`evidence_ids` (file, line); `memberships` map each `COMP-` id to its `MOD-` ids.

**Reason.** `report` without `archkeel.toml` exits 2 and asks for `init`, which writes a draft. A
newcomer must see what is there first. A contract with no rule decides nothing; PASS is false.

**Rejected.** A second renderer or a server. An implicit `init` or a contract file in the
repository. Components from a file walk (a second collector). A mark by contract file name.

**Limits.**
- TypeScript and Dart are not detected: explore exits 2 and names `tsconfig.json` or `pubspec.yaml`.
- An import edge is not a call edge or a runtime order. No order comes from reachability.
- An unresolved call stays an unresolved relationship and a coverage gap, not a missing edge.
- Entry points are `__main__` modules only; `pyproject.toml` scripts are not read.
- `report` on a contract with components but no rule now gives UNKNOWN, not PASS.
- Git can refresh its own index file when explore reads the worktree state.

**Checks.** `tests/test_explore.py` and the demo row `explore-contract-free`.
