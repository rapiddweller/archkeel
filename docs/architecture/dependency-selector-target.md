# Dependency selector API Target

Issue #541 adds bounded, independently authored API intent to
[the IR Target](contracts/ir.json). Its dependency declarations express the
intended API directly; they are not generated from observations.

The `dependency-policy` component owns `archkeel.ir.dependency`: the
`SelectorMatch` and `DependencyTargetKind` enums, immutable
`ModuleSelection`, `DependencySelection` and `DependencySelector`,
the `ComponentOwnership` alias and the shared `module_in_ownership`
primitive. These seven named exports are its public surface. Importing another
name through that module, including a name it imports for its own use, crosses
the interface boundary.

The independent UML declarations pin the enum members, selector mode/kind
fields, selection fields and method signatures. They also govern the model's
compatibility wrappers and `ForbiddenDependencyRule.selector` property.
Module names, package names and symbols remain string data. Ownership tuples
and generic iterable inputs remain typed containers; they do not require
artificial DTOs.

`codec_contract.parse_dependency_selector(Record) -> DependencySelector`
is the named record-to-domain conversion seam. Its raw record inspection and
wire string validation remain codec responsibilities. The dependency module
does not decode JSON, issue receipts or decide verdicts. Core retains verdict
authority; projections consume the shared typed selection. The new
`boundary_types` rule covers exactly the dependency module's declared public
surface. This change adds no raw-input allowance or wildcard IR exemption.

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
