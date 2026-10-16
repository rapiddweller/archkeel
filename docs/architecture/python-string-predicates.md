# Written string predicate evidence

The Python construct collector owns the closed `_StringPredicate` vocabulary and
`_string_predicate(ast.Call) -> _StringPredicate | None`. It decodes the written
member name once per classification; unknown names remain unclassified. The enum
value is emitted only as the existing `form` metadata.

The existing `string_literal_compare` policy also covers `startswith` and
`endswith` when their first positional argument contains an observed string or
bytes scalar, literal tuple element, direct qualifying module tuple or ordinary
local Enum value. A mixed literal/typed tuple retains its literal evidence.
Named tuples require one direct non-empty literal binding and lexical ownership.
Their visible loads must be membership operands or the first predicate argument;
aliases, reassignment, mutation, computed containers and shadowing invalidate the
claim. Lists and sets retain membership-only qualification.

Only the first positional argument is inspected. Range and keyword arguments do
not establish prefix/suffix vocabulary. Typed Enum arguments and parameter data
remain data. The observer classifies written member-call syntax; it does not prove
the receiver is a runtime string, validate argument types or infer computed values.
No additional AST traversal, parser wrapper or runtime type authority is added.

The small independent Python Target names the actual enum and decoder signature.
Native source mutations must fail that fixed Target when its enum or return type
widens. The new predicate constructs use the existing module-scoped policy, proven
by actual-source failure controls. Function-only construct selectors are not
supported; no whole-module typed-control claim is made for this Python owner.
Other existing Python construct vocabularies remain outside this increment.
