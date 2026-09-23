# AD-94: Boundary types resolve static aliases

`boundary_types` unwraps `Annotated`, checks `Literal` constants, and follows statically
recognized top-level aliases. Dynamic and ambiguous bindings remain UNKNOWN. On Archkeel's
self-scan on merged main, `unknown_positions` changes from 24 to 18 and
`calls_unresolved` is 499. The baseline records these measured values;
`typing_positions` remains 53.
