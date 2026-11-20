# AD-923 Cycle rules read pair gaps with a possible return path

**Decision.** A pair gap `a -> b` with two observed ends holds a cycle rule only when `b` can
reach `a` at that rule's level and the possible cycle can reach a member of the rule's scope and
return. Use all known imports and all possible pair edges together. A component edge needs two
different, unique owners. An internal pair does not add a component edge.

Reuse the return-path calculation in `native/model/src/pair_gaps.rs`. The global drop rule still
checks for a return at any active level. A rule checks only its own level and scope. An observed
cycle still gives FAIL. A possible cycle gives UNKNOWN, not FAIL.

**Reason.** A kept pair used to hold both cycle rules, even when it could not close a cycle at
either level. A module cycle inside one component does not justify holding the component rule.

**Rejected.** Check only known return paths: two possible edges can close a cycle together.
Keep every pair for both levels: an unrelated gap gives no reason to hold a cycle rule.

**Limit.** A pair with an unobserved end still holds both rules. Other scope limits and the verdict
of the whole run do not change. The upper graph can contain paths that no single execution takes.

**Tests.** `native/eval/src/gap_scope_tests.rs` checks single and joint possible edges, a scoped
cycle, an observed cycle, and an unobserved end. `native/eval/src/drop_rule_tests.rs` checks an
internal pair that holds the module rule but not the component rule.
