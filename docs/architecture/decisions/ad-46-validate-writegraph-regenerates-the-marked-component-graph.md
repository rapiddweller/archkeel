# AD-46 `validate --write-graph` regenerates the marked component graph after a contract edit

`validate --write-graph` regenerates the single marked Mermaid graph in provenance
docs from sorted `observed_component_edges`. It shares `mermaid_edges` with `init`
and `_marked_bodies` with drift diagnostics. The CLI writes returned files and
names the page as an artifact. An identical sorted graph is not rewritten.

Only diagram declarations, `%%` comments and plain `_GRAPH_EDGE` edges are accepted.
Keep the declaration and ordered comments ahead of sorted edges; add `graph TD` if
missing. Preserve bytes outside the block, apart from normalizing page line endings
to `\n`. Drop blank lines inside. Read and write UTF-8
([AD-7](ad-07-determinism-is-measured-not-assumed.md)).

Other syntax, including subgraphs, labels, `classDef` or `linkStyle`, leaves the page
untouched. `graph.drift` identifies the unsupported line and asks for a manual edit.
Zero or multiple marked graphs remain `graph.count`; do not guess the intended page.
Validation rereads a rewritten page, so fixing its sole drift finding yields exit 0.
The graph is written even when other diagnostics retain exit 2: it records imports.

Issue #2, from DATAMIMIC CE onboarding at 0.4.1, exposed the missing regeneration
command. `validate` already owns contract, observation and docs; `report` does not.
Regenerating the full block would lose chosen directions such as `flowchart LR`.
A denylist cannot safely reorder Mermaid syntax that binds edge indices or scopes;
keeping labeled and plain copies would duplicate edges. Sorting also normalizes a
valid but hand-ordered graph, making subsequent runs idempotent.

Limits: styled graphs require manual edits even when their styling is harmless;
CRLF pages change every line. Comments move ahead of edges.
Checks: CLI regeneration preserves `flowchart LR`, sorts six renamed-shop edges and
writes nothing on repeat. Validation tests cover init parity, marker count, missing
declarations and unsupported syntax. Self graph parity and `validation-graph-count`
use the shared reader. This page's original graph regeneration only sorted eight edges.
