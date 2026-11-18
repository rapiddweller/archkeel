# AD-933 The renderer does not own frame results

**Decision.** Make `html` and `engine_frame` sibling modules. Keep the frame and
error types in `engine_frame`. The renderer reads JSON, not the writer's result
types. Remove `Clone`, `Debug` and equality from `Outcome`: production callers
read its decision and violations and do not use these traits.

**Reason.** The renderer was a child of `engine_frame`. Possible execution of the
writer's traits gave the renderer a return path through that parent. The evaluator
had the same problem with `Outcome` in its crate root. Its tests can print the
decision directly.

**Rejected.** Exempt trait execution from the cycle rules, or put the writer and the
renderer in one component. Both options hide a dependency that can matter in other code.

**Limit.** The renderer's module path changes in the scan inventory. Each added
entry pairs with a removed entry of the same kind and reason after the path
rename. The module cycle rule still has possible return paths.

**Tests.** The native self-scan checks the component rule. A test adds the return
edge in a temporary copy of the native tree. The rule must fail and cite both
observed edges.
