# Planned component policy fixture

This fixture models owner policy before its source package exists. Its `components[]` records carry
the same planned API and `requires` declarations through promotion. `fixture-source` owns only the
small observed stub module; it does not make source-level checks for `mcp` PASS.

The UML Target keeps structural intent as children of the canonical `mcp` owner.

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
```
