# Browser architecture

The observed graph has no edges. Collection gaps make it incomplete.

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    explorer["explorer"]
    scene["report-scene"]
    graph_scene["graph-scene"]
    deviations["atlas-deviations"]
    layout["layout"]
```

The target graph shows the dependencies permitted by the browser contract.

<!-- archkeel-target-graph -->
```mermaid
flowchart LR
    explorer["explorer"]
    scene["report-scene"]
    graph_scene["graph-scene"]
    deviations["atlas-deviations"]
    layout["layout"]
    explorer --> scene
    explorer --> layout
    scene --> graph_scene
    scene --> deviations
    deviations --> graph_scene
```
