# AD-125: Target hierarchy is physical presentation

Status: approved. Alex accepted the rendered CE preview on 1 October 2026.

Target combines semantic components and declared `root_layout` frames. Frames describe physical
placement. They do not create owners, dependency edges, or architectural layers. Component IDs,
requirements, verdicts, and Actual/Target/Diff identity stay unchanged.

Placement uses declared namespace/package scopes and layout declarations only. Its status is
`declared`, `inferred`, `multiple`, `ambiguous`, or `unmapped`. Ambiguous and unsupported scopes
remain one explicit unplaced card. Missing declared children and folded layouts stay inspectable.
Details expose the exact `public`, `requires.through`, rationale, and provenance values.

Dependency order comes from semantic `requires` before physical frames are drawn. If a cycle leaves
nodes unranked, retain every node and edge and say: “Dependency order unresolved: cycle or
dependency on a cycle.” An unranked dependent is not thereby cyclic. A null rank is presentation
metadata; it does not change a verdict or mean UNKNOWN.

The shared explorer uses one Details panel. A single activation selects; Enter, double-click, or
Open selected drills one level. Fullscreen uses the browser API when available and a bounded
window fallback otherwise. Both preserve explorer state; the fallback also restores page scroll
and focus. Measured text stays inside cards and package headers. A compact header may abbreviate
an overflowing label; Details retains the full identity and responsibility for pointer, keyboard,
and touch users. Relationship paths try bounded detours around the visible header instead of being
masked underneath it. An unsolved route stays visible with a separate renderer warning; it does not
change architecture evidence or status.

Diagram may show populated physical frames for navigation, but placement is proven from observed
module names: every module in a card must lie within the frame's declared namespace. Only the
uniquely resolved frame and its populated ancestors render. This never imports Target-only
components, absent children, requires edges, or dependency ranks into Diagram; its cards and edges
remain observed evidence, and unassigned inventory stays independently reachable. Target retains
declared placement and responsibilities. Responsibility text is shown unchanged as an annotation,
not observed behavior or a verdict input. Existing declared Diagram cards with zero observed
modules remain visible but do not prove observed existence or populate physical frames. Diff
remains the evidence for absent declarations.

Refresh screenshots from merged source and run integrated release gates before publication.
