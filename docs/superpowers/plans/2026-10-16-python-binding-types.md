# Python binding control types

Issue: #542. Base: c0bea80b212fec40af2509dc06a5460bef71a4c2.
Branch: fix/542-python-binding-types.

## Approved scope and owners

- Source owns a small binding_types model: nominal import and lexical binding kinds,
  compiler scope kinds, and the existing immutable AliasBinding value.
- Existing Source/scopes algorithms retain all binding and namespace-proof authority.
  Import collection produces ImportKind. Lexical lookup explicitly maps it to BindingKind.
- The external symtable kind is decoded at its existing read boundary; an unrecognized
  value returns no known kind. AST nodes continue to use nominal isinstance checks.
- Necessary consumers: source.py, scopes.py, imports.py, resolve.py and calls.py.
- Property, receiver-origin, annotation and dynamic-target grammars are later increments.
  Remaining raw grammar in source/scopes/calls/resolve is documented as pending.

## API and compatibility

- Target names and module paths remain strings. Internal control fields become Enum types.
- Human reason text preserves the existing enum word through output-only value rendering.
  No control branch compares .value or raw parser strings.
- Preserve the existing source.AliasBinding and scopes.BindingKind re-export ports.
- Do not change constructor validation, compiler claims, namespace inference, source receipts,
  measurement budgets, or rule evaluation semantics.
- The root enum-placement rule adds only the explicit new model owner. The inner Python
  Source owner exposes the typed binding port. Contract deltas are additive and isolated.

## Steps

1. Commit this plan before production code.
2. Native RED: actual collected repository sources still contain raw comparisons in the
   six binding-only control functions; actual import/lexical bindings expose string kinds.
3. Implement the owned nominal model and migrate producers/consumers.
4. Add a whole-module native guard only for the new complete model, plus explicit owned
   AliasBinding.kind and NameBinding.kind Target annotations.
5. Check native raw-dispatch mutations and kind-to-str widening against unchanged Targets.
   Function-level observation controls do not claim a whole-module PASS for pending sources.
6. Run collector/scopes/source-binding/enum-literal/trust/hygiene regressions, Ruff, Mypy and
   native validation with unchanged 65 unknown / 919 unresolved / 0 violations.
7. Return the clean intended commit and exact contract deltas for independent Astra review.

## Verification discipline

Real native records and trace-valid violations supply the RED/GREEN evidence. No fake
observation, hand-authored comparison result, blanket exception or copied JSON history.
The temporary hosted workflow stays on a verification branch, outside the product tree.
