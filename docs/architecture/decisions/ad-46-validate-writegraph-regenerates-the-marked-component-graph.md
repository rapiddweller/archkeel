# AD-46 `validate --write-graph` regenerates the marked component graph after a contract edit


With the flag, `run_validate` replaces the edges of the one marked Mermaid graph among the
contract's provenance documents by `observed_component_edges` for the current contract, sorted by
`mermaid_edges`, the one formatter `init`'s `architecture_document` now calls too. It rewrites a
block only when every non-blank line is a diagram declaration (`graph` or `flowchart`), a `%%`
comment or a plain edge `_GRAPH_EDGE` reads: the declaration and the comments stay ahead of the
edges, a block without a declaration gets `init`'s `graph TD` on top, and everything outside the
block stays byte for byte. Any other line, a `subgraph`, a labeled edge `a -->|uses| b`, a
`classDef` or `linkStyle`, makes it write nothing: `graph.drift` stands, and its remedy names that
line and says to edit the edges by hand. Validation then reads the rewritten page, so a run whose
only finding was `graph.drift` exits 0. `run_validate` returns `(RunResult, files)` the way
`run_init` does, the CLI writes both through one loop and `artifact` names the page; a graph already
in that form is not written. `_marked_bodies` is now the one reader of where a marked block starts
and ends, used by `graph_diagnostics` and by the writer alike, so the two cannot disagree about
which block is the graph, and the `graph.drift` remedy names the command whenever the command can
act. Provenance documents are read as UTF-8 explicitly, since the page goes back out as UTF-8
whatever the locale is ([AD-7](ad-07-determinism-is-measured-not-assumed.md)).
Reason: `validate` demands a marked graph equal to the observed component edges, but only `init`
wrote one, so every later contract edit that merges, splits or renames a component left
`graph.drift` to be fixed by hand although `validate` already computes the exact edges it compares
against: issue #2, found onboarding `datamimic_ce` with 0.4.1, and the internal-service finding that
no command regenerates the graph after a component cut.
Rejected: `report --write-graph`, because `run_report` never parses the contract into an
`ArchitectureContract` or reads its provenance documents, it only receives the analyzer's
observation, and it writes evidence under `test-artifacts/`, not the repository's own pages;
`validate` holds the contract, the observation and the documents already. Regenerating the whole
block as `init` writes it, because both marked graphs in this repository, this page's and the shop
sample's, chose `flowchart LR`, and a regenerated block would silently redraw every page that is not
an `init` draft. Writing a marker into a page that has none, or picking one of several marked
graphs, because both guess which page the architect meant; `graph.count` already names either state.
A denylist of `subgraph` and labeled edges, rewriting around them, because Mermaid has more
statements bound to an edge's position or scope than those two (`linkStyle` counts edges by index,
`a --> b --> c` and `a --> b & c` chain them), and a reordering that misses one silently changes
what the diagram says; an allowlist of three line kinds fails closed on every statement it cannot
read, including the ones not thought of yet. Keeping a labeled edge and adding the plain one beside
it, because the graph would then draw the pair twice. Writing only when the edge set differs,
keeping a hand-ordered graph that already validates, because the output would then depend on the
page's history; one sorted form makes the command idempotent, and a second run writes nothing.
Limit: a styled graph, even one whose `classDef` or `style` lines depend on no edge position, is
left to a human, because the allowlist does not tell harmless statements from binding ones; comments
keep their order but move ahead of the edges, and blank lines inside the block are dropped. The page
is written with `\n` line endings, so a CRLF checkout sees every line change. The page is written
even when other diagnostics keep `validate` at exit 2, because the graph records observed imports,
not decisions.
Check: `tests/test_cli.py::test_validate_write_graph_regenerates_only_the_marked_graph` renames the
shop sample's `render` to `view` in the contract, sees exactly one `graph.drift` naming the command,
then exit 0 with the page byte-identical up to the marker, `flowchart LR` kept and the six edges
sorted, and a second run writing nothing;
`tests/test_validation.py::test_write_graph_writes_the_graph_init_writes` and
`::test_write_graph_changes_nothing_without_exactly_one_marked_graph` pin `init`'s form and the
zero-or-several case; `::test_write_graph_adds_the_declaration_a_block_lacks` gives a block holding
only a `%%` comment and an edge its `graph TD`, and
`::test_write_graph_leaves_a_block_it_cannot_read_to_the_architect` writes nothing for a `subgraph`,
a labeled edge or a `classDef` and names that line in the hand-edit remedy;
`tests/test_self.py::test_component_graph_matches_observed_edges` and the catalog's
`validation-graph-count` row still hold on the shared reader. This page's own graph was regenerated
with the command, which only sorted its eight edges.

