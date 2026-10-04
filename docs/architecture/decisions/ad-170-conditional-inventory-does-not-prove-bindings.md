# AD-170 Conditional inventory does not prove bindings

The Python collector visits definitions in every statement branch. Each site keeps
its lexical parent and ordered `DefinitionContext` values: syntax kind, branch and
source evidence. Repeated names remain separate definitions. Nothing is executed.

`ArchitectureGraph`, its codec and generated schema retain those contexts. The
shared renderer displays their cards, operations and evidence. Contexts describe
observed source; independent Target declarations cannot assert them as facts.

Calls and references treat conditional namespace definitions as candidates. Core
returns UNKNOWN for their Target availability and relationship endpoints. Existing
contract rules keep their conservative definition view. Conditional module names
become opaque binding candidates for legacy type checks. The canonical inventory
keeps one real definition, including names that shadow builtins. Old replacement
binding records cannot overwrite it. Public API and unused-symbol claims do not
infer availability. The compatibility view is not another persisted model.

Classifier roles under control flow, exhaustive inventory capabilities, lexical
binding proof and static instances remain open. Coverage stays partial. PR #277's
SourceFacts/Core boundary is unchanged.

Proof: `tests/test_conditional_definitions.py`, `tests/test_uml_rendering.py`;
`make check`, `make report-browser`, `make self-observation`, `make self-validate`.
