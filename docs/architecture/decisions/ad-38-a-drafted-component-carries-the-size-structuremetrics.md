# AD-38 A drafted component carries the size `structure_metrics` already measures, so the architect sees what a per-child draft hides before deciding whether to consolidate

`draft_contract` groups in-scope modules by the direct child directories it
already uses for draft components, then calls `ir.structure.scope_metrics`.
This shares declared-component aggregation and uses the existing observation,
without another scan ([AD-10](ad-10-the-report-draws-component-flow-as-intent-against.md)).

The generated table adds Modules and Inner edges; `init --json` adds `draft_sizes`;
the terminal names the unique module-count leader or says none stands out.
This lets the architect question directory-based grouping before committing it.

The analyzer draft had three components (`bridge`, `embedded`, `runtime`), but
`embedded` held 18 modules. The `ir` draft had 14 components and 182 open decisions;
`check` had 12 and 132, though the architect chose three children. Bare names hid
which child needed consolidation. Measuring after writing the contract is too late;
printing every size buries the outlier.

Directory grouping remains reproducible but cannot distinguish unrelated purposes
within one child. Connectivity-based grouping remains open.
Checks: onboarding's `test_init_drafts_component_sizes_and_names_the_largest`,
terminal's leader and tie tests, and self-contract/public-proposal parity in
`tests/test_self.py`.
