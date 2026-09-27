# AD-115 Nested API lifecycle uses local evidence

With a local `interface_boundary`, nested `public` and `planned` entries use the same
lifecycle checks as root entries (#182). The evidence belongs to the mounted level.

Use means a cross-sibling import or explicit publication by a child, parent or ancestor
facade physically inside the current parent. A function may be defined elsewhere and
re-exported by that facade. An unrelated facade, arbitrary parent import or publication
outside the parent cannot make a local entry used.

AD-120 also accepts a real outside consumer of a directly published child API,
but only through every ancestor boundary it crosses. The same module may serve
as the parent facade and child API without a re-export wrapper.

The analyzer records scoped publisher/type evidence on existing symbol facts, using the
existing facade resolver. Validation consumes those facts and mounts the existing diagnostic
pointers. No per-level rescan, second resolver or root-baseline exemption for matching labels.

The optional Python import fact `source_binding_unique` preserves existing binder evidence.
It distinguishes a published constant import from a same-name rebind, without guessing a
symbol kind. Direct and conditional rebinds cannot prove publication. Older observations
remain readable; a missing fact supplies no new proof. Analyzer profile `0.56.0` names this
observation change, not a new Archkeel package release.

Publication reuses the root facade predicate, including private-name and nonempty literal
`__all__` restrictions. Proven re-export chains may cross an unassigned intermediate module;
only uniquely owned local targets count. Ordinary Dart imports do not publish names and do
not acquire Python binding facts. Existing root export semantics remain unchanged.

A missing module stays `interface.missing`; a built, unused public entry is `interface.unused`.
A built but unused planned entry stays target work. Reaching it asks for promotion through
`interface.planned_built` without granting access. Unknown import names are not proof of non-use.

Independent tests cover repeated labels, constants, ancestor facades, re-exported definitions,
unrelated signatures and partial profiles. Four recursive demo variants show public/planned
entries with and without a consumer.

Under the architect's evidence-backed budget authorization, the self call budget moves
531 → 536. `validate --against 704e364` attributes the net five to added source operations:
scoped evidence lookup, parent-publication lookup, two string operations over recorded names,
and parent-component accumulation. A renamed target accumulator appears once as added and
once as removed. This is changed code, not improved detection. Self-validation retains
41 UNKNOWN positions, 0 violations, 0 cycle edges and 53 typing positions; no violation
exemption or rule is relaxed.
