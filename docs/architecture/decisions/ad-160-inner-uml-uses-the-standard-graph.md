# AD-160 Inner UML uses the standard graph

As-Is modules and Contract 2.2 Target entities render from `ArchitectureGraph`.
Diff uses the same cards and routes, with assessments from Core's recorded comparison.
The browser never compares source facts with intent or turns missing evidence into PASS.

`ir.target_records` owns projection of authenticated Target records. Core and render
call it instead of maintaining separate conversions. IR performs no I/O or policy.
Render's scene contains display geometry; it does not replace or persist architecture facts.

Class and interface cards have attribute and operation compartments. Signatures retain
parameter kinds, unevaluated defaults and visibility. Inheritance uses a solid line and
hollow triangle; realization uses a dashed line and hollow triangle. Other directed
relationships retain their kinds and sites. Selection dims unrelated elements. Visible
paths and hit paths share geometry. Package navigation has no invisible frame targets.
Cycles and their downstream nodes stay unranked instead of creating false layout depth.
Cards limit long signatures to two lines; Details retains complete values.
Fit centers the selection with readable text; larger graphs remain pannable.
Outside methods/functions fold into their recorded class/module, retaining every site
and endpoint in Details. Symbols without lexical parents stay separate; labels prove no ownership.

Core assessments remain separate from source resolution. Diff displays known unlisted
definitions and retains UNKNOWN. Source sites without endpoints stay in Details.
The existing Component/Module Target projections and legacy Diff tree remain supported;
their complete migration into the standard graph is still open. AD-161 adds typed component
intent without turning ownership/API selectors into source facts or required calls.

Proof: `tests/test_uml_rendering.py`; `make report-browser`, `make self-validate`
and `make self-observation`. No new runtime dependency or analyzer policy was added.
