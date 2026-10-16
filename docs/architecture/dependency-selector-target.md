# Dependency selector API Target

Issue #541 adds bounded, independently authored API intent to
[the IR Target](contracts/ir.json). Its dependency declarations express the
intended API directly; they are not generated from observations.

The `dependency-policy` component owns `archkeel.ir.dependency`: the
`SelectorMatch` and `DependencyTargetKind` enums, immutable
`DependencyOwner`, `ModuleSelection`, `DependencySelection` and `DependencySelector`,
the `ComponentOwnership` alias and the shared `module_in_ownership`
primitive. These eight named exports are its public surface. Importing another
name through that module, including a name it imports for its own use, crosses
the interface boundary.

`DependencyOwner(identity, modules)` gives the policy API a named ownership input.
The identity is an opaque caller-provided key; it may be a label or identifier and
is returned unchanged. Its modules are the shared `ModuleSelection`, keeping
package and exact-module ownership in one representation. The model's
`dependency_owners` adapter converts legacy tuples, preserving order and
duplicates. Report preparation adapts ownership once before selecting policies.

The independent UML declarations pin the enum members, selector mode/kind
fields, selection fields and method signatures. They also govern the model's
compatibility wrappers, the typed adapter signature and
`ForbiddenDependencyRule.selector` property.
Module names, package names and symbols remain string data. Ownership tuples
and generic iterable inputs remain typed containers; they do not require
artificial DTOs.

`codec_contract.parse_dependency_selector(Record) -> DependencySelector`
is the named record-to-domain conversion seam. Its raw record inspection and
wire string validation remain codec responsibilities. The dependency module
does not decode JSON, issue receipts or decide verdicts. Core retains verdict
authority; projections consume the shared typed selection. The new
`boundary_types` rule covers exactly the dependency module's declared public
surface, including both `DependencyOwner` parameters. The legacy model's generic
ownership aliases and adapter input retain their typed compatibility signatures;
their deep alias proof remains outside this bounded policy boundary. This change adds no raw-input allowance or wildcard IR exemption.

The native tests copy the actual dependency source and selected model/codec
declarations into a disposable repository retaining `archkeel.ir` identities.
They keep the authored Target fixed while changing Python annotations or an
outside consumer import. Correct declarations receive PASS for the protected
type/signature aspects; a mode field or parameter changed to `str`, a selection
return changed to `tuple`, a selector property changed to `str`, and an
unpublished import produce trace-valid native violations.

This is not a closed inventory of all IR members or relationships. A missing
method under a class with partial member evidence remains UNKNOWN; the tests
do not change observations or manufacture complete coverage. Unspecified
behavior, semantic equivalence, structural Protocol conformance (#356),
remaining broad governance exports and the complete inner architecture Target
(#340) remain outside this guarantee. Existing unknown and coupling budgets
are unchanged.
