# AD-178 Target navigation projects the standard graph

The renderer must not reconstruct architecture intent from declaration records
after Core has published an authenticated `ArchitectureGraph`. Components,
parents, layout permissions and file inventories have one semantic source.

`render.target` projects that graph into navigation cards. `render.html` embeds
the result and report evidence. The browser's shared scene renderer owns layout,
UML symbols, routes and interaction. Core still owns authentication, comparison
and verdicts; source adapters do not import presentation or policy.

File names resolved by Core remain presentation aliases. They assert no class,
call, file existence or dependency permission. This alias bridge and the older
browser controllers remain migration work; this decision does not claim the
whole report already consumes only the standard graph.

ArchKeel's render contract defines projection, HTML, summary and terminal
responsibilities and their dependency direction. The target is agent-proposed
from the agreed separation of concerns; it is not an automatic copy of Source.

Proof: graph-input projection tests, existing physical navigation/browser cases,
`make self-observation`, `make self-validate` and `make check`.
