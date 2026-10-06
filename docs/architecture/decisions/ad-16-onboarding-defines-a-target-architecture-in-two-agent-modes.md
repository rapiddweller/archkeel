# AD-16 Onboarding defines a target architecture in two agent modes, and every decision records who made it

The contract states the target architecture; reports measure violations against it.
The architect owns that target. Recommendations use repository evidence and quality
goals, and ask for unknown goals when they would change the recommendation. Goals
belong in rationales until a rule can evaluate them. The CLI remains deterministic
and never decides dependencies.

The skill has two modes:

- Interview: read ADRs and architecture docs, propose components, layers and allowed
  directions, then ask for one confirmation. Ask further questions only about
  conflicts or missing intent, with a recommendation and `path:line` source.
  Ask why before recording any deviation from the recommendation, especially one
  contradicting docs, prior decisions or code; record the answer as the rationale.
- Auto: decide open pairs from docs, then confirmed or documented layer principles.
  Observed dependencies never imply permission.

Each rule requires `decided_by: architect` or `agent`. Validation and reports count
agent decisions awaiting review; later interviews ask only those. The architect
chooses a first auto draft, focused interview or later review.

The first internal-service interview overwhelmed its architect with 20 unranked
rounds for 156 pairs. An unmarked draft then hid 122 agent rationales as intent.

Check: required `decided_by`, report counts, the skill's deviation questions, and
pair-by-pair comparison of an auto draft with the 156 architect decisions.
