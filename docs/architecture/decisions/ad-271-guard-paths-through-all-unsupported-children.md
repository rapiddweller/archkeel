# AD-271 Record the calls in every child of an unsupported statement

**Decision.** For `for`, `while`, `try`, `with` and `match`, the guarded-path walker now
visits every child node, not only direct statements and expressions. It also enters the
nodes between them: except handlers, `with` items and `match` cases. A call found there gets
a record with the reason `unsupported_control_flow` and no condition value, as a call in a
`for` body already did. The path keeps the unsupported statement and any guard test inside it.

**Reason.** The walker handled a child only when it was an `ast.stmt` or an `ast.expr`.
Except handlers, `with` items and `match` cases are neither, so the walker skipped them. On
`src/archkeel` and the standard library (8,437 functions, 54,166 calls) 1,441 calls
(2.7 %) had no record. Each one sat under an except handler, a `with` item or a `match` case.
After the change the count is 0. A rule of kind
`forbidden_effect_under_condition` must see such a call to say that it cannot decide.

**Effect on existing reports.** The new records have no condition value, so they never create a
violation. In the tested shapes (an effect call in an except handler, a `with` item or a `match`
case, next to a clean allowed path) the rule verdict is `UNKNOWN` before and after the change.
What changes is the record: an explicit `unsupported_control_flow` unknown, where there was
none. Projects without a guarded rule are not affected.

**Rejected.**
- A list of the node types to enter (`ExceptHandler`, `withitem`, `match_case`): a new Python
  node type would again be silent.
- Support for these constructs, with real conditions: this needs a decision for each construct
  and has no evidence of need.

**Check.**
- `tests/test_guard_path_classes.py`: ten new statement kinds (except type, `try` else and
  `finally`, `except*`, `with` item and target, `match` guard, subject and nested `try`, `for`
  else) in the same equivalence-class checks; every call in every kind gets a record; a guard
  inside an unsupported block keeps the statement and its test on the path.
- Expected tables changed in two rows only: `try` (the call in the handler is new) and `match`
  (the call in the case is new).
- 20 of these tests fail on the walker before this change.
