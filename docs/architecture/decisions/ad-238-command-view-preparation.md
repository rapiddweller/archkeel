# AD-238: Command-view preparation has a focused owner

`ir.report_projection` derives the authenticated architecture sheet, including
ownership, scoped requirements and uncertainty. Compact command presentation
changes for separate reasons: selector abbreviation, permission grouping, reason
interning and result-envelope adaptation.

Move the command DTOs and preparation helpers together to `ir.command_view`,
inside the existing governance component. It consumes shared projection and
result values; it does not construct reports or evaluate architecture policy.
Callers import them from `ir.command_view`; `ir.report_projection` keeps no
aliases. `ir.codec` imports the focused command owner directly
and owns JSON serialization. Private helpers stay private to their implementation.
Runtime annotations remain resolvable in eager import orders.

Rejected: putting command envelopes in the shared projection vocabulary, which
would mix presentation into shared values; wrappers or another interface, which
would duplicate an existing pure seam; lazy imports to hide a dependency cycle.

Limit: this changes physical responsibility only. Wire schemas, compact/full
and selected JSON bytes, reason order, selectors, evidence identity, UNKNOWN
scope grouping and authenticated relationship summaries remain unchanged.
The nested IR contract assigns the module to governance without expanding its
public surface or changing policy and baseline limits. The fail-closed widening
classifier mechanically flags the added ownership selector. The issue-525 v2
amendment binds exactly this authorized ownership migration to the prior and
current contract trees, with identical baseline digests; it grants no additional
public interfaces, imports, through selectors, Any positions or budget debt.

`tests/test_command_view.py` checks eager type hints,
frozen compact/full/selected bytes, reason interning, permission and selector
negative controls, scoped uncertainty and missing-projection rejection.
Existing architecture-projection, schema, agent-JSON, saved-report and native
filter tests retain the authenticated report and rendering contracts.
