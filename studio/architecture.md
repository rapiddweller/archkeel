# Studio architecture

Studio presents the system model and checked stories. Navigation, map and story components use the
state, model, API and DOM components. The presentation components call each other. The core decides
architecture rules and verdicts.

Navigation reads the current map view and requests focused connections. The map sends selected
connections to navigation to open their evidence. Both components use the DOM path formatter.

The Studio server has no current schema for its query endpoints. The system contract does not declare
an interface for them until a schema describes the actual messages.

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    n_0["navigation"]
    n_1["map"]
    n_2["story"]
    n_3["state"]
    n_4["model"]
    n_5["api"]
    n_6["dom"]
    n_0 --> n_1
    n_0 --> n_2
    n_0 --> n_3
    n_0 --> n_4
    n_0 --> n_5
    n_0 --> n_6
    n_1 --> n_0
    n_1 --> n_2
    n_1 --> n_3
    n_1 --> n_4
    n_1 --> n_5
    n_1 --> n_6
    n_2 --> n_0
    n_2 --> n_1
    n_2 --> n_3
    n_2 --> n_4
    n_2 --> n_5
    n_2 --> n_6
    n_3 --> n_4
    n_5 --> n_4
```
