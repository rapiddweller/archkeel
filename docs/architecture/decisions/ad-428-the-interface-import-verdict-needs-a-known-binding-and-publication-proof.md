# AD-428: The interface import verdict needs a known binding and publication proof

Status: accepted

## Context

The core names `interface_boundary` as an unsupported rule kind.
The reference engine can accept an import without symbol proof in some profiles.
That behavior cannot establish a core PASS.

## Decision

The model selects imports between two different, uniquely owned components.
It skips a target without `public`, an excluded type-only import and a source outside its domain.
It also skips an import that a forbidden-dependency rule rejects.
One model judgement serves both the evaluator and the existing `Scope::complete` proof.
A known violation stays FAIL beside an incomplete scope.

A PASS requires a known binding and a proven route to the public name.
This slice accepts direct witnessed names and known static module-object imports.
A module-object grant matches exactly one source and target module, never a named import.
The existing export-list restriction, coverage, ownership and pair proofs still apply.
Interface and dependency receipts share the exactly-one-owner proof in `receipts::ownership`.
No new proof maker exists.

Typed gaps name an unread binding, an unproven publication route or an incomplete publication surface.
An included type-only import, namespace binding, star barrel, alias route, default re-export,
`require` or dynamic import cannot establish a PASS without the required proof.
The Rust collector supplies no complete publication surface, so this rule remains UNKNOWN there.
The Rust collector does not change.
The TypeScript collector adds the missing known bit for static imports without bindings.
Such an import binds no name, so a symbol selector can change from UNKNOWN to PASS.
A whole-module prohibition still rejects the side-effect import with FAIL.
It uses the existing import fact; namespace bindings remain unknown.
The collector also withholds a direct witness when an unread declaration can merge with the named declaration.
Separate type/value declarations and overload signatures retain the runtime implementation witness.
Import expansion preserves known script-global facts instead of replacing them with a module-object result.
An exact module-object grant can PASS beyond the Python profile, which reports `rule-unsupported-by-profile` for grants.
This is deliberate: the collector now proves that the selected import binds no name and names exactly that module.
Path aliases without binding proof, `export =` and declaration merging remain UNKNOWN, never a grant-based PASS.

Public-interface lifecycle validation is not part of this import verdict.
Facade signature types and unused public entries remain outside this port until deletion stage D2.
The core retains its existing profile limits for that surface and for symbol selectors.
This slice does not port `public_api.py` or `facade_signature_types`.

## Alternatives and limits

Do not copy a profile shortcut that skips targets with symbol-level public entries.
Do not treat an absent binding or export witness as permission.
A later slice can prove cross-module publication routes and complete export surfaces.
This slice keeps those routes UNKNOWN instead of inferring a re-export.
An unrelated public module cannot authorize a known direct import of a private module.
No Python decision code grows.

## Checks

`tests/test_native_interface_boundary.py` checks direct imports, module objects and exact grants.
It plants private crossings in forms without publication proof.
The native self-row test retains its pin because its contract has no rule of this kind.
