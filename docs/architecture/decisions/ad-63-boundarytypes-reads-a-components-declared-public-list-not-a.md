# AD-63 boundary_types reads a component's declared public list, not a naming convention

Select `boundary_types` subjects from declared component public lists, not naming conventions.
Accept resolved provider-declared types, enums and models; `planned` does not become a facade. Reuse
the same subject predicate for evaluation and presence checks: zero subjects is UNKNOWN, never
vacuous PASS.

Signature exposure resolves the usage conflict in
[AD-65](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md); undecidable positions follow
[AD-67](ad-67-an-undecidable-boundary-position-is-unknown-not-silence.md). Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).
