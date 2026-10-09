# Render target

Core publishes authenticated architecture data and comparison receipts. Rendering
changes no verdict. `render.atlas` builds the compact Atlas payload;
`render.html` composes the offline report. The existing outer public API stays
unchanged. HTML and terminal output share result explanations from `render.summary`.

The browser consumes one authenticated `ArchitectureReport` for As-Is, Target
and Diff. Missing authenticated Target data cannot produce a Target diagram.
Source paths are observations; Target files are independent intent. Open
decisions and external permissions keep their meaning.

Overview aggregation, relationship filters and Focus change the scene. Details
retain import sites and referenced operations. Diff navigation may show unowned
observed namespaces without inventing ownership or a comparison receipt.

The [render contract](contracts/render.json) enforces Python component ownership
and dependency direction:

- `atlas.py`: compact Atlas payload; no HTML dependency.
- `summary.py`: shared result explanations; no output dependency.
- `html.py` / `terminal.py`: compose their output from those inputs.

The offline browser assets have separate responsibilities:

- `report-scene.js`: report indexes and scene projection; preserves Core facts.
- `report-layout.js`: ELK placement, geometry validation and manual routing.
- `flow.js`: card measurement, DOM, input, navigation and layout lifetime.

Scene and layout accept explicit inputs without reading Explorer state. Browser
tests exercise these boundaries and the integrated report. The Python collector
does not inspect JavaScript assets; its checks do not prove browser dependencies.
[AD-213](decisions/ad-213-renderer-responsibility-boundaries.md) records this split.
[AD-179](decisions/ad-179-reports-render-one-graph-boundary.md)
defines the shared report boundary. The [UML target](uml-model-target.md) records
capabilities and remaining work.
