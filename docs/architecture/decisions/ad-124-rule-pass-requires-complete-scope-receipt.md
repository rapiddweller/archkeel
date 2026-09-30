# AD-124 A rule PASS requires a complete scope receipt

`complete_requires` and `interface_boundary` receive PASS only when their evaluator
records a receipt for a non-empty scope with complete scan coverage and unique
ownership. A single component with no crossings still has a completed evaluation.
Empty scopes, missing declared packages, partial containing scopes, ambiguous owners,
and unowned modules have no receipt. A blank-source Python package initializer is
the sole unowned-module exception; lack of recorded static imports alone does not
prove that an initializer has no runtime side effects or dynamic imports.

The aggregate `declared_rules` verdict is UNKNOWN when any non-declaration rule
assessment is UNKNOWN, even when no counted unknown position explains the missing
receipt. A known violation remains FAIL, and incomplete observations remain UNKNOWN.

This changes analyzer output; `ANALYZER_VERSION` rises to `0.60.0` (AD-3).
