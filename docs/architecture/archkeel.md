# Archkeel architecture

[The contract](../../architecture-contract.json) owns component boundaries.
Its public API lists the model and codec modules available to the analyzer.
Within-component imports remain allowed.
The analyzer component owns the bundled Python analyzer. Raw AST records stay inside that
component; its public result is the typed `ObservationResult`.

The core components `ir` and `check` have no adapter or presentation dependencies. `check`
receives the analyzer and host adapters through typed ports; the CLI wires their concrete
implementations. Shared host evidence values and validation belong to `ir`.

`render` owns deterministic HTML projections and may import only `ir`. The CLI orchestrates
commands and writes report artifacts.
