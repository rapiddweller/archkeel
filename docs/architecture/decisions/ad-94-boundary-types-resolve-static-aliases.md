# AD-94: Boundary types resolve static aliases

`boundary_types` unwraps `Annotated`, checks `Literal` constants, and follows statically
recognized top-level aliases. Dynamic and ambiguous bindings remain UNKNOWN. On Archkeel's
self-scan this changes `unknown_positions` from 24 to 23. The alias collector adds two
unresolved calls to the self-scan (`calls_unresolved` 497 to 499), from its uppercase-name
checks. The self-validation budget records those measured values; `typing_positions` is
unchanged.
