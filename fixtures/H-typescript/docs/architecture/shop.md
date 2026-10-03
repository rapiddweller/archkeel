# Shop dependency contract

The app composes data and presentation. Data and presentation depend on domain. Domain knows neither. Data adapters stay independent.

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    app --> data
    app --> presentation
    data --> domain
    presentation --> domain
```
