# AD-38 A drafted component carries the size `structure_metrics` already measures, so the architect sees what a per-child draft hides before deciding whether to consolidate


`draft_contract` maps every in-scope module to the child directory `init` would name a
component, the same grouping it already builds to name the components themselves, and
passes that grouping to `ir.structure.scope_metrics`: the aggregation `structure_metrics`
uses for a declared component, generalized to any caller-supplied scope so a draft measures
the same way a contract does once it exists. No second scan runs; the modules and edges were
already in the one observation `init` made ([AD-10](ad-10-the-report-draws-component-flow-as-intent-against.md)). The two numbers travel to the three
places an architect or agent reads a draft: the generated table gains Modules and Inner
edges columns next to each component, `init --json` gains `draft_sizes`, and the terminal
prints one line naming the drafted component whose module count uniquely leads, or that none
does. Reason: measured on this repository, `init --source src/archkeel/analyzer --namespace
archkeel.analyzer` drafts 3 components — `bridge`, `embedded`, `runtime` — while `embedded`
alone holds 18 of the scope's modules, a fact the three bare names do not carry; `init` on
`src/archkeel/ir` drafts 14 components and 182 open decisions; `init` on `src/archkeel/check`
drafts 12 components and 132 open decisions, where the architect settled on the 3 named in
`src/archkeel/check/architecture-contract.json`. An agent consolidating a draft into a few
sub-components had to reread the source tree to find which child was worth folding into
which; the draft itself said nothing about size. Two cheaper ways were rejected. Recomputing
size from the drafted contract once it is written asks `validate` or `report` to do it, but by
then the draft is already committed to a directory-per-component shape with no size signal to
question it against. Naming every drafted component's size in the terminal, the way the open
decisions list does for pairs, buries the one number worth reading under as many lines as
there are components; one line naming the largest keeps the summary the length of the other
onboarding lines. Limit: `init` still proposes one component per direct child directory, not
by import connectivity between modules; a large, well-connected child still becomes one
draft component and a directory split across two unrelated purposes still becomes two,
because grouping by directory is what makes the draft reproducible from names alone. Whether
a sub-root draft should instead group modules by which ones import each other, so a size
outlier could also be a cut point instead of only a number, is open. Check:
`tests/test_onboarding.py::test_init_drafts_component_sizes_and_names_the_largest`,
`tests/test_terminal.py::test_terminal_view_names_the_largest_drafted_component` and
`test_terminal_view_says_no_drafted_component_stands_out_on_a_tie`, and
`tests/test_self.py::test_self_contract_public_matches_drafted_proposal`, which still passes
with `draft_contract` returning a third value.
