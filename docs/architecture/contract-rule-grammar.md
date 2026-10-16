# Contract rule grammar

ArchitectureRuleKind and DecisionMaker are shared architecture-graph values. Contract rule
variants refer to fixed members of that vocabulary, so a forbidden-dependency rule cannot
be typed as a different rule variant. The contract codec validates JSON and constructs
these nominal values before dispatch; evaluators consume the typed model.

CompatibilityLifetime belongs to the compatibility-shim model. CycleLevel describes the
cycle grammar: an explicit component level normalizes to the existing absent default;
only the module level is stored on NoComponentCyclesRule. Existing canonical contract
bytes and accepted values remain unchanged.

JSON keys, component and module names, field paths, annotation text and amendment authors
are data. Field presence is interpreted by codec_wire and distinguishes an absent field
from explicit null. Annotation exceptions retain their exact existing grammar, including
the three native mapping shapes. Module-target path grammar has one authority in
architecture_graph.validate_module_target.

The authored IR Target states the rule discriminants and attribution types independently
of source observations. Native checks prove the real source API against this intent and
reject widening a field to str under the same contract. A codec string-control guard is
claimed only after the integrated source, including the separate version grammar, passes
the actual module check. There is no whole-model guard claim.
