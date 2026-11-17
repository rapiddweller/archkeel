# FastAPI 0.163.0 component graph

Static layering of the package at the pinned tag (generated from the import scan).

<!-- archkeel-component-graph -->
```mermaid
graph TD
  api --> compat
  api --> dependencies
  api --> middleware
  api --> openapi
  api --> telemetry
  compat --> api
  compat --> openapi
  dependencies --> api
  dependencies --> compat
  dependencies --> security
  openapi --> api
  openapi --> compat
  openapi --> dependencies
  security --> api
  security --> openapi
  telemetry --> api
```
