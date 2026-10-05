# AD-188 Nested permissions pin the complete field

Issue #342: a union member cannot stand in for its field declaration. The typed verdict retains
both, correlated by finding before deduplication. Parent DTOs prefix paths without replacing leaf
annotations. Exact matching uses collected text, including proven Optional spellings.

A field selector must reach one declaration before matching members or container depth, including
clean and UNKNOWN declarations. A compound-field permission selects one outer map. Multiple maps,
ambiguous same-path fields and alias expansions stay unallowed; other bad members and UNKNOWN
remain visible. Allowance FACTs retain the selected member when it differs from the declaration. Finding IDs stay unchanged.

No contract or wire-schema migration. Core semantics advance to 0.72.0 under AD-3.
Check: `tests/test_boundary_type_nullable_fields.py`; existing direct/contained allowance tests.
