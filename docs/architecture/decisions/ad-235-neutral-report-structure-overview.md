# AD-235 Report component sizes as a neutral structure overview

The former report review question compared a component's module count with the
number of top-level components, or its internal module edges with cross-component
edges. Those quantities describe different abstraction levels. A component with
17 modules and no internal edges could become a candidate solely because the
contract contained fewer components; this does not establish a boundary defect.

Show every measured component in a neutral **Structure overview**, using Core's
`structure_metrics` for module, internal-edge, incoming, outgoing and unresolved
call counts. Retain the existing Core top-level component and directed component
pair counts as separate context. Keep canonical component routes, including
selection in a parent scope for leaf components. The legacy evidence page also
retains package measurements without the size review question.

Missing module evidence is unavailable. Missing dependency edges leaves known
module counts visible and labels edge-derived counts `n/a`, never zero. The
overview infers no suspicious component, split recommendation, PASS or FAIL.

Reject hiding the measured sizes or simply softening the candidate label: both
would leave readers without either useful measurements or a neutral presentation.
Do not introduce a replacement threshold, score, renderer or Core claim schema.
The recorded `oversized_insides` claim and its API remain compatible; the report
reads its top-level counts, not its candidate selection. Rules are unchanged.

This decision addresses [#518](https://github.com/rapiddweller/archkeel/issues/518).
[#384](https://github.com/rapiddweller/archkeel/issues/384) remains open for separate
Used elsewhere/Hub hint review and calibration.

Proof: [structure report tests](../../../tests/test_structure_report.py).
