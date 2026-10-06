# Render target

Core publishes authenticated architecture data and comparison receipts. Rendering
changes no verdict. HTML and terminal output share result explanations from
`render.summary`.

The browser uses one `ArchitectureReport`, scene projector, navigator and SVG
renderer for As-Is, Target and Diff. Missing authenticated Target data cannot
produce a Target diagram. Source paths are observations; Target files are
independent intent. Open decisions and external permissions keep their meaning.

Overview aggregation, relationship filters and Focus change the scene. Details
retain import sites and referenced operations. Diff navigation may show unowned
observed namespaces without inventing ownership or a comparison receipt.

The [render contract](contracts/render.json) enforces dependency direction.
[AD-179](decisions/ad-179-reports-render-one-graph-boundary.md) defines the shared
report boundary. The [UML target](uml-model-target.md) records capabilities and
remaining work. Core tests check source sites and findings; browser tests exercise
the shared renderer.
