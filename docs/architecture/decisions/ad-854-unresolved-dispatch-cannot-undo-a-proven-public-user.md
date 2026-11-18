# AD-854 Unresolved dispatch cannot undo a proven public user

## Decision

When every selected public item already has a proven or stated external user, an internal
dispatch gap between two observed modules does not hold that `unused_public` rule.
Keep the gap in the report and in every other rule receipt that reads it.

## Reason

Dispatch can add a user. It cannot add a declaration or undo a proven use.
The existing inventory, scope, and user receipts still apply.

## Alternative

Keep all pair gaps in the rule receipt. That gives UNKNOWN even with a user for each item.

## Check

The Rust compiler accepts both fixtures. With a proven user for every public item,
`unused_public` passes. With another public type whose user is unclear, it stays UNKNOWN.
The dispatch gap is visible in both reports.
