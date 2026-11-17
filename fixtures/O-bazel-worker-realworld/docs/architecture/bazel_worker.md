# bazel_worker layering contract

The architecture as built at the pinned commit, written for the ArchKeel benchmark.

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    core --> driver
    core --> worker
    driver --> core
    worker --> core
```
