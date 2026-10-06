# AD-21 Structure measurements are derivations, never gates

`ir` derives module counts, inner edges, fan-in, fan-out and unresolved-call share
per component and package from modules and module edges. Reports show them; no rule,
verdict or exit code depends on them. The same applies to drawing measurements.

Global ratios hide local gaps: across 50 self-reports since 0.2.0, the global
unresolved ratio improved four times while a component worsened. At 0.3.0 it ranged
from 8.4% in `ir` to 41.8% in `cli`, around 19.1% globally. Gating these numbers would
invite refactoring for a score, contrary to the roadmap.
Check: derived numbers sum to observation totals; `ir` performs no I/O
([AD-17](ad-17-archkeels-own-target-names-its-quality-goals-and-ir-holds.md)).
