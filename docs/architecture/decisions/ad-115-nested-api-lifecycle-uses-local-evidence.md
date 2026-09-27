# AD-115 Nested API lifecycle uses local evidence

With a local `interface_boundary`, nested `public` and `planned` entries use the same
lifecycle checks as root entries (#182). The evidence belongs to the mounted level.

Use means a cross-sibling import or explicit publication by a child, parent or ancestor
facade physically inside the current parent. A function may be defined elsewhere and
re-exported by that facade. An unrelated facade, arbitrary parent import or publication
outside the parent cannot make a local entry used.

The analyzer records scoped publisher/type evidence on existing symbol facts, using the
existing facade resolver. Validation consumes those facts and mounts the existing diagnostic
pointers. No per-level rescan, second resolver or root-baseline exemption for matching labels.

A missing module stays `interface.missing`; a built, unused public entry is `interface.unused`.
A built but unused planned entry stays target work. Reaching it asks for promotion through
`interface.planned_built` without granting access. Unknown import names are not proof of non-use.

Independent tests cover repeated labels, constants, ancestor facades, re-exported definitions,
unrelated signatures and partial profiles. Four recursive demo variants show public/planned
entries with and without a consumer.
