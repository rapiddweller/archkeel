# AD-180 Relationship exploration retains evidence

As-Is and Target cards keep names, kind and counts. Details retains complete responsibilities
and opens on selection. Incoming and outgoing rows open the connection's evidence.
Hover and keyboard focus preview direct neighbors without rebuilding the graph or
changing the pinned selection. Connected cards and lines stand out; unrelated items recede.
Node and edge selections carry an explicit type because a containment declaration can share
its component's ID. Dimmed lines retain evidence but cannot intercept background clicks.
Inside a component, its breadcrumb owns the scope; the parent is not repeated as a peer card.
Containment stays in the contract details. Only edges with two drawn endpoints get hit paths.
Touch selects directly. View switches restore the
matching legend.

The explorer follows independent verdicts. As-Is replaces the generic Diagram label.
Both graph views project their source records into one plain `RenderScene`:

- Nodes: stable source ID, UML kind, label, metadata, tooltip and presentation rank.
- Packages: ID, scope, parent and member IDs; bounds come from layout.
- Relationships: ID, source, target, kind, evidence state and tooltip.

One renderer owns measurement, package layout, cards, UML symbols, routing and emphasis.
Every dependency uses its collision-checked router. Row-pair lanes reserve separate arrival
heights; outer destinations get earlier lanes. Detours prefer free stretches and cannot reverse
their departure direction. Browser tests check actual crossings, shared stretches, arrowheads
and hit geometry in the small call graphs and the own class model. Dense scenes still need review.
The controller owns navigation, dragging and evidence selection. Source projections retain
the observed and declared identities; no second persistent architecture model is introduced.
Existing Observation records, declarations, findings, coverage and evidence remain the source
for As-Is, Target and the distinct Diff categories.
This presentation boundary is compatible with the proposed source-facts/Core split in
[PR #277](https://github.com/rapiddweller/archkeel/pull/277). The renderer imports neither
language adapters nor policy implementations; it does not assemble canonical observations.
The process protocol and source-facts extraction remain outside this change.

Target uses declared dependency levels,
UML component and package symbols, and dashed dependency arrows with fixed-size open heads
and a solid terminal stem. Its blue accent
identifies declarations, not conformance. Cycles remain explicitly unranked.
Files use UML artifact symbols; observed classes use a compartmented class symbol.
Dependencies do not imply inheritance or composition. Interfaces remain in Details;
detached socket/circle decorations are omitted. A single outer package uses its header
without a redundant outline; nested package boundaries stay visible.
Background dragging pans without changing card positions. Narrow views disclose
filters and the legend; explorer scrollbar tracks stay hidden.

Drilled components and packages show directly connected outside neighbors.
The renderer projects exact module imports from the existing observation, including
declared external libraries. It preserves counts, rule ids and source samples.
A violation applies only to its contributing import evidence; absence of a finding
does not prove conformance. Outside cards add no owner, boundary or permission.
Local inventory counts exclude them, and Back restores the scope that opened them.

`tests/test_uml_visual_acceptance.py` covers selection, hover, touch, exact crossings,
label collisions and return navigation. `make report-browser` includes these checks.
