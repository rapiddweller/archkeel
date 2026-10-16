# Python binding control types

Issue: #542. Base: ff4cae52451f43550639959b6f87a77f96375597 (PR #551 collector-wire carrier).
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
- Preserve valid legacy constructor spellings while storing nominal kinds; do not change compiler claims, namespace inference, source receipts,
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
   native validation with unchanged 58 unknown / 918 unresolved / 0 violations.
7. Return the clean intended commit and exact contract deltas for independent Astra review.

## Verification discipline

Real native records and trace-valid violations supply the RED/GREEN evidence. No fake
observation, hand-authored comparison result, blanket exception or copied JSON history.
The temporary hosted workflow stays on a verification branch, outside the product tree.

## RED evidence

- Plan committed before production code: 5fcec26602e6d0667e034ffaf7ea1f290b4fe834.
- Corrected native setup observes the complete real module before selecting the six binding-only functions; function-only source selectors deliberately receive no module coverage guarantee.
- RED 38943076148: 11 expected failures, no collection/setup failures. Two public Literal field annotations, two producer/lookup string-kind cases, six trace-backed native string dispatches, and an unknown compiler scope authorizing a module fallback.

## Integration boundary

- Final integration rebases the binding-only changes onto the current collector-wire carrier ff4cae52451f43550639959b6f87a77f96375597. Root policy updates append to that carrier; no stale whole-contract overlay is used.
- The independent physical-source-line evidence correction is a separate PR and is not part of this increment. Its future import and parse_sources line-view deltas remain independent of these binding changes.
- Previous broad verification on the old carrier: 555 passed / 6 skipped; final narrow verification: 70 passed, Ruff, Mypy, and unchanged 65/919 baseline. These counts are historical evidence only; the final carrier must retain its own 58/918 baseline.

## Final verification on the current carrier

- Hosted run 38947855629, candidate 6a248271958c8af77caf425d204b603414548b5b: 629 passed / 6 skipped; Ruff clean; Mypy clean for 133 source files. The canonical formatter produced an empty patch.
- Native validate against ff4cae52451f43550639959b6f87a77f96375597 generated the normal v2 amendment and the following no-write replay succeeded. Exit 0, no diagnostics or failures; 918 unresolved / 58 unknown / 52 typing / 0 violations. Baseline bytes and budgets are unchanged.
- Actual before/after reports were produced from the exact carrier worktree and candidate. The unresolved call-site multiset keyed by source file, callee expression and reason is identical: no added or removed sites. Calls analyzed 18169→18172, resolved 14801→14804, partially resolved 2450 unchanged; AST coverage 100% and rules PASS remain.
- Contract changes add one exact enum-owner placement, one complete-model raw-control guard, three consumed Source ports and nine independently authored Target entities. No broad Source-module PASS or arbitrary namespace inference is claimed.
- The temporary verification workflow is excluded from the product tree.

## Astra constructor compatibility correction

- Reproduce both previously valid string-kind constructor APIs before changing production.
- Normalize AliasBinding.kind and NameBinding.kind exactly once in their frozen dataclass
  post-init methods, using their existing nominal Enum constructors and
  builtin-qualified object.__setattr__. Unknown values raise ValueError.
- Retain nominal field annotations, enum identity, re-export identity and immutable values;
  no union field types, shared converter framework or resolver authority is introduced.
- Preserve the two browser assertions from the actual #551 base
  7b2a14de58eb18be716c8eadef5c43928ec464a5.
- Verify legacy and nominal inputs, defaults, invalid values and the real lexical consumer;
  then existing binding/native Target controls, Ruff, Mypy, and normal amendment replay
  against the actual #551 base with no additional unresolved calls or budget changes.
