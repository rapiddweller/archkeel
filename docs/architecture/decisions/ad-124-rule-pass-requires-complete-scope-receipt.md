# AD-124 A rule PASS requires a complete scope receipt

`complete_requires` and `interface_boundary` receive PASS only when their evaluator
records a receipt for a non-empty scope with complete scan coverage and unique
ownership. A single component with no crossings still has a completed evaluation.
Empty scopes, missing declared packages, partial containing scopes, ambiguous owners,
and unowned modules have no receipt. A Python package initializer with no AST
statements (empty, comment-only, or whitespace-only) is the sole unowned-module
exception. Docstrings and imports are statements and keep their ownership
obligation; lack of recorded static imports alone does not prove that an
initializer has no runtime side effects or dynamic imports.

The aggregate `declared_rules` verdict is UNKNOWN when any non-declaration rule
assessment is UNKNOWN, even when no counted unknown position explains the missing
receipt. A known violation remains FAIL, and incomplete observations remain UNKNOWN.

Python scope proof follows physical directories and the recorded module identity.
An unmappable observed domain cannot be omitted from completeness checks.

Initial receipt support used analyzer `0.60.0`; AST-empty and physical-path
corrections use `0.62.0` (#232, #233; AD-3).
