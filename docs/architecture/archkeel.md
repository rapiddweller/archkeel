# Archkeel architecture

[The contract](../../architecture-contract.json) owns component boundaries.
Its public API lists the model and codec modules available to the analyzer.
Within-component imports remain allowed.
The producer component owns the bundled Python analyzer. Raw AST records stay inside that
component; its public result is the typed `ObservationResult`.

The core components `ir`, `check`, and `analyzer` produce typed evidence without presentation
dependencies. `render` owns deterministic HTML projections and may import only `ir`. The CLI
orchestrates commands and writes presentation files.
