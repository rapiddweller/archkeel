# Typed unresolved-call directions and terminal assessment decisions

Issue #542 includes parser and protocol control. Reuse model.KnownSemanticChangeKind
for the existing two-value UnresolvedCallChange port through a narrow Literal subset.
Normalize supported legacy constructor strings once in the existing dataclass; reject
other action kinds instead of broadening added/removed. Ratchet production, validation
and human summary consume the canonical members. The terminal consumes the existing
RuleAssessmentStatus owner. Public SemanticChange.change remains future-open text.

The independent Target protects the actual direction field. Four exact function guards
protect the consumed decisions; source mutations must fail unchanged authored intent.
No new enum, DTO, physical product module, duplicated action inventory or debt allowance.
Preserve AD-100 row JSON, count/sign/order/error behavior for supported inputs.
