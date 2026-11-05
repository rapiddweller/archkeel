# AD-304 Planned component targets promote to package owners

**Status.** First slice for issue #846; full pre-promotion API and dependency-policy modeling
remains open. Checked against the contract and target graph on 2026-11-05.

**Decision.**
- UML may declare a component only with `presence: planned`, responsibility, and provenance.
- Its child entities and supported structural UML relationships remain independent target intent.
  The planned owner is not a source observation and does not claim package ownership.
- UML `requires` remains invalid. Before promotion, UML can describe structural interfaces and
  signatures; it cannot declare component `public`/`planned` API selectors, forbidden
  responsibilities, or allowed dependency permissions.
- Promote by removing the UML component entity and adding a `components[]` owner with the same
  ID, concrete package or exact-module ownership, and any API or `requires` declarations. The
  existing component contract then owns and enforces those fields. Child UML parent IDs remain
  stable across the edit.
- A referenced/defined UML component is invalid. The transition is an authored contract edit;
  ArchKeel does not infer package creation or migration history. Existing scanned-package
  reference checks remain unchanged.

**Rejected.** An unscanned package placeholder would imply ownership and trigger current package
checks. UML dependency permissions would create a second source for `requires`.

**Limits.** Pre-promotion UML expresses target structure, not component API ownership or dependency
policy. The public fixture demonstrates target-only intent and the authored promotion shape. It
does not prove implementation, package discovery, or source compatibility.

**Validation.** `tests/test_target_graph.py` covers planned target, invalid presence, structural
relationship, and promotion through existing owner fields. `tests/test_validation.py` retains
the missing scanned-package diagnostic.
