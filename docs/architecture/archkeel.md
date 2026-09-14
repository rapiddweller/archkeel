# Archkeel architecture

[The contract](../../architecture-contract.json) owns component boundaries.
Its public API lists the model and codec modules available to the analyzer.
Within-component imports remain allowed.
The producer component owns the bundled Python analyzer. Raw AST records stay inside that
component; its public result is the typed `ObservationResult`.
