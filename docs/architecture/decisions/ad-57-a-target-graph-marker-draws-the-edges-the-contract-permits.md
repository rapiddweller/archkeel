# AD-57 A target graph marker draws the edges the contract permits

`validate` compares the one marked Mermaid graph after `<!-- archkeel-component-graph -->`
against `observed_component_edges`: what the code does. Under a target-first contract that set
also carries the edges the target forbids, known debt the architect has not yet paid down, so a
page that draws it draws a forbidden edge as if it belonged. A second, independent marker,
`<!-- archkeel-target-graph -->`, is added beside it: `graph_diagnostics` and
`rewrite_component_graph` now walk both, and `_marked_bodies` takes the marker it looks for
instead of hardcoding one, so both read the same span-finder and can never disagree about where a
block starts and ends. `target_component_edges` is the new marker's source: the component pairs
the contract permits, taken as the union of every `requires` entry
([AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md)) and every pair an
`allowed_dependency` rule decides
([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md)). The two are not the
same set - closed-world's `allowed_dependency` is one half of a decision made for every ordered
pair, while `requires` is the narrower, more intentional list a `complete_requires` rule makes
complete by absence - but a contract writes one system or the other in practice
(`ir.decisions.requires_declared` gates which), so the union needs no branch on which: a
`requires`-based contract carries no coarse `allowed_dependency` pair and a pair-decided one
carries no `requires` entry, and the union reduces to whichever the contract actually wrote. A
contract that has adopted neither permits nothing yet, so its target graph is empty, and a page
that draws no target marker at all is unaffected - the marker is optional, `graph.count` only
answers when the target marker is found more than once, while the observed marker keeps its
original, always-exactly-one rule. `graph.drift`'s subject now names the marker it is about, for
example `docs/architecture/shop.md (target graph)`, so a reader knows which graph to fix.
`--write-graph` rewrites each marker independently, from its own edges, leaving a block untouched
that is missing, ambiguous, or holds anything but a declaration, a `%%` comment and an edge
([AD-46](ad-46-validate-writegraph-regenerates-the-marked-component-graph.md)); the two markers
may share one page, which then comes back once with both blocks rewritten. `init` writes no target
marker: it drafts no dependency rule and no `requires` entry, so there is no permitted set yet to
draw, and writing one would decide pairs the architect is supposed to decide
([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md)). The shop sample's own
page now carries both markers, since Archkeel's own contract's target already equals its eight
observed edges and a second, identical graph there would say nothing; the shop sample is where the
demo catalog routinely makes the two disagree.

Reason: [issue #16](https://github.com/rapiddweller/archkeel/issues/16) - a target-first contract's
observed set includes the edges it forbids, so the one marked graph either has to draw known debt
as if it were the architecture, or the page cannot show the target at all.

Rejected: comparing `<!-- archkeel-component-graph -->` against `target_component_edges` instead of
`observed_component_edges`, redefining what the existing marker means. Every page that carries it
today asserts what the code does; redefining it would silently change that assertion for every one
of them, with no diagnostic marking the change, and would break AD-46's writer, which regenerates
that marker from observed imports specifically. [AD-49](ad-49-an-allowance-may-name-its-module-exactly-so-a-package-root.md)
rejected the same move for `allowed_sources` for the same reason. A single marker that draws both
graphs stacked, or a `--target` flag that switches `<!-- archkeel-component-graph -->`'s meaning
per invocation, because either still redefines one marker's meaning depending on context, which a
reader cannot see from the page alone. Deriving the permitted set from `allowed_dependency` alone,
ignoring `requires`, because Archkeel's own contract, and any contract that has adopted
`complete_requires`, would then draw an empty target graph although it has decided every pair by a
different means; deriving it from `requires` alone fails the opposite contract the same way.

Limit: the target graph is not itself validated against the code, so a permitted pair with no
`requires` entry's rationale reviewed and no `allowed_dependency` rationale reviewed either - a
contract that has adopted neither system - draws nothing and reports nothing; the target marker is
then simply absent-shaped, not wrong. A pair narrowed below component level, by a `target_symbol`
or `allowed_sources` on a `forbidden_dependency`, or by `requires`'s own `through`, still decides
only the coarse component pair for this graph, the same narrowing `observed_component_edges`
already lived with. Two markers on one page double `_marked_bodies`' scan of it, which is cheap
compared with the analyzer pass beside it.

Check: `tests/test_validation.py::test_target_graph_matches_the_edges_the_contract_permits`,
`::test_target_graph_drift_names_the_target_marker`,
`::test_a_page_with_only_the_observed_marker_behaves_exactly_as_before`,
`::test_write_graph_regenerates_both_marked_graphs_on_one_page` and
`::test_write_graph_leaves_a_target_block_it_cannot_read_to_the_architect` cover the marker in
isolation; `tests/test_cli.py::test_validate_write_graph_regenerates_both_marked_graphs` and
`tests/test_architecture_demo.py::test_graph_drift_names_the_command_or_the_line_it_refuses` and
`::test_target_graph_drift_leaves_the_observed_graph_untouched` cover it through the CLI and the
demo catalog's `validation-target-graph-drift-write-graph` and
`validation-target-graph-drift-subgraph` rows, beside the existing
`validation-graph-drift-write-graph` and `validation-graph-drift-subgraph` rows, which now drift
both markers at once since the shop sample's target and observed graphs agree today.
`docs/architecture/shop.md` carries both markers as committed evidence that a page can draw both.
