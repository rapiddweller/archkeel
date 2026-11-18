# AD-911: Keep the proven receiver type when recording a Rust call

**Reason.** Two calls can have the same text and reach the same file but use different types.
For example, `value.label()` can use `Clean` in one function and `Profile` in another.
The previous import key kept only the first call. A ban on `Profile` then depended on
the order of the functions.

**Decision.** Include the proven receiver type in the import key for a resolved dot call.
Use the lexical module and type name that the existing resolver supplies. Calls with the same
path, target and type still share one import record. Keep the same key for path calls and other
imports. A path can already have an identical lexical import at the same site.

**Rejected.** Keep every occurrence of a call. The rule needs one record for each distinct
dependency, not one record for each use of that dependency.

**Limit.** This change adds no receiver proof. It does not narrow any unknown trait or derive
dispatch.

**Check.** `test_same_call_text_keeps_both_proven_receivers` runs both function orders with
`rustc`. Both must report the banned `Profile` dependency, while the program calls both members.
