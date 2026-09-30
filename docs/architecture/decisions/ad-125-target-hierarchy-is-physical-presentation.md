# AD-125: Target hierarchy is physical presentation

Status: candidate. The projection is approved; browser behavior and the rendered candidate remain
under review before implementation merge.

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

The candidate browser behavior uses 100% initial zoom, native scrolling, collapsed accessible
Details, and preserves selection and navigation identity across Actual, Target, and Diff. Test
these behaviors on the rendered candidate before merge. No screenshot is approved by this decision.
