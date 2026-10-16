# Owned graph and assessment vocabulary

Graph control vocabulary belongs to architecture_graph. Entity and relationship kinds,
visibility, origin, presence, resolution, completeness, versions and assessment aspects
have distinct nominal types. AssessmentStatus is shared with model.RuleVerdict through
the existing facade. Completion PASS/FAIL, comparability SUPPORTED/UNKNOWN and the
four-state RuleAssessmentStatus retain their different meanings.

DecisionMaker names the architect/agent contract role. ArchitectureRuleKind owns the
existing contract rule tags so graph declarations and later contract parsing share
identity without a graph/model import cycle. Amendment.decided_by remains free-form.

Graph wire parsing uses enum constructors once. The two old string-choice loops are
removed. Existing graph dataclasses normalize valid legacy constructor spellings;
builders and UML consumers publish and branch on owned enum values. Module names,
paths, annotations and extension language spellings remain data. Known profile language
decisions consume the shared collector Language type.

Historical graph/comparison/report schemas preserve their values, ordering and subset
domains. Subset fields use Literal of owned enum members. Valid wire versions,
reference validation, inventory evidence and UNKNOWN semantics remain unchanged.

Whole-module native guards protect architecture_graph, graph_codec, target_graph and
check.uml_compare. Independent authored Target entities define enum ownership and
retain existing public field/return intent. Native widening mutations and parser
equality/membership/match/string-alias probes demonstrate enforcement.

Source graph and UML evidence adapters consume these graph values. Their unrelated
profile-record grammar remains part of the open #542 migration; these guards do not
claim complete protection of those adapters or of presentation-only vocabularies.
