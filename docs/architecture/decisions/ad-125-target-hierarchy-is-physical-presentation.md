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

The explorer uses one Details panel. One activation selects; Enter, double-click or Open selected
drills one level. Fullscreen uses the browser API or a bounded window fallback. Both preserve
state; the fallback restores page scroll and focus. Text stays inside cards and headers.
Overflowing headers may abbreviate labels; Details retains full identity and responsibility
for pointer, keyboard and touch users. Routes try bounded detours around headers. An unsolved
route stays visible with a renderer warning, without changing architecture evidence or status.

Diagram placement requires every observed module in a card to lie within the frame's declared
namespace. Only uniquely resolved frames and their populated ancestors render. Target-only
components, absent children, requires edges and dependency ranks never enter Diagram. Its cards
and edges retain observed evidence; unassigned inventory remains reachable. Target retains declared
placement and unchanged responsibility annotations, which prove no behavior and affect no verdict.
Declared Diagram cards with zero observed modules remain visible but prove no existence and populate
no frames. Diff retains absent declarations.

Refresh screenshots from merged source and run integrated release gates before publication.
