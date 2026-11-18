# AD-927 Request read errors need no `Debug` trait

**Decision.** Remove the unused `Debug` implementation of `Unread`. The core converts a
read error into its existing overflow or I/O message by matching the variant.

**Reason.** No caller formats `Unread`. Its `Debug` implementation gives the crate root a
possible execution edge from other modules. That edge can close a cycle through the root
and expose more possible targets.

**Rejected.** Move the implementation to another module. There is no caller that needs it.
Exempt a `Debug` implementation from the proof. In other code, callers can execute it.

**Limit.** Other possible cycles remain. The collector still reports an unresolved pair to
`snapshot.work` when it cannot rule out a destructor. For some existing pairs this cause
replaces the former trait execution cause; it does not add a module pair.

**Tests.** The core tests for request limits and process output check the read paths. The
native self-scan checks the effect on both cycle rules and the gap inventory.
