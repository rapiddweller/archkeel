# AD-304 Planned component owners carry policy before code

**Status.** Issue #846 target-owner policy model. Checked against the contract and target graph on
2026-11-05.

**Decision.**
- Keep the existing UML-only planned component form valid for structural target intent. The
  package-less `components[]` form below adds owner policy. One identity cannot be declared in both
  forms at once.
- A component may be declared before code with `lifecycle: planned` and empty `packages`. It is
  the same `components[]` owner used after implementation, not a second UML policy source.
- Reuse its existing `planned` API selectors, `forbidden_responsibilities`, and `requires`. Planned
  API selectors identify their target modules directly; duplicate selectors across owners are
  invalid. UML remains structural and may describe child interfaces and signatures under that
  owner.
- `packages` and `exact_modules` continue to mean observed source ownership. Promotion keeps the
  component ID and policy, removes `lifecycle: planned`, and supplies concrete package or exact
  module ownership. Child UML parent IDs remain stable.
- Schema and target checks can validate declarations before code. API existence and dependency
  compliance require source evidence; an unscanned planned owner cannot pass source-level rules.
  Missing evidence remains UNKNOWN.
- `lifecycle` requires Contract 2.4.0 and an explicit graph/report 1.3.0 wire value. Legacy lifecycle
  fields stay absent. Graphs 1.0–1.2 retain their existing interpretation; graph 1.3 requires the
  explicit value for a package-less owner. Current reports expose source-rule UNKNOWN by scope,
  not as a per-component verdict.
- A referenced/defined UML component is invalid. Promotion is an authored contract edit; ArchKeel
  does not infer package creation or migration history. Existing scanned-package reference checks
  remain unchanged.

**Rejected.** Treating planned packages as scanned ownership would imply source evidence that does
not exist. UML dependency permissions would create a second source for `requires`.

**Limits.** Pre-promotion declarations do not prove implementation, package discovery, or source
compatibility. Dependency permissions remain target policy until source is observed.

**Validation.** `tests/test_target_graph.py` covers planned owner policy, selector conflicts,
round-trip, promotion, and UNKNOWN source checks. `tests/test_validation.py` retains the missing
scanned-package diagnostic.
