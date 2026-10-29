# AD-279 A catalog target only compares or indexes its arguments

**Status.** Proposed. The owner approves it.

**Decision.** The Python symbol collector records `parameters_contained` on each function and
method (#751). The flag is true only when both conditions are true:
1. Each read of a parameter in the body is a subscript index (`OPTIONS[key]`) or a comparison
   operand (`key == x`, `key in KNOWN`).
2. The body stores or deletes no subscript (`d[k] = v`, `del d[k]`).

The walk includes nested functions, lambdas and classes, because a closure can give a parameter
away. It checks every parameter, because the policy accounts a member argument at any formal.

The `catalog_argument` policy (AD-251, AD-277) accounts a member argument only when the selected
operation makes no call and no write, and has `parameters_contained: true`. A missing flag counts
as false.

**Reason.** `def read_option(key): return key` gave PASS, but the caller got the member back:
`read_option(OptionKey.PAGE_SIZE)._value_ = 'x'` changed it. `key.__dict__['_value_'] = 'x'` in
the target also gave PASS, because a subscript store has no write record.

**Effect on the rules.**

| Selected operation body | Rule | Before | After | Kind |
|---|---|---|---|---|
| returns the argument, a value derived from it, or a container that holds it | `catalog_argument` | PASS | UNKNOWN | correct |
| gives the argument to a local alias, a `yield`, an `await` or a lambda | `catalog_argument` | PASS | UNKNOWN | correct |
| any subscript store or delete | `catalog_argument` | PASS | UNKNOWN | correct |
| returns another parameter that got the member | `catalog_argument` | PASS | UNKNOWN | correct |
| a slice bound, a truth test or `.value` of a parameter | `catalog_argument` | PASS | UNKNOWN | strict |
| only comparisons and subscript indexes of the parameters | `catalog_argument` | PASS | PASS | correct |

An attribute store, a global store and a call to another function were UNKNOWN before. They stay
UNKNOWN.

**Rejected.**
- Record a fact for each parameter read. It adds many records, and the policy needs one answer.
- Follow the returned value to its callers. It needs a data-flow analysis for one rule.
- Check only the selected parameter. The policy accounts a member at any formal.

**Limits.** A comparison or an index runs `__eq__`, `__contains__` or `__getitem__` of the other
operand. The collector does not follow these methods, so a custom operand can change the member
and still give PASS.

**Check.**
- Tests: `tests/test_catalog_target_parameters.py` (`test_target_that_gives_away_*`,
  `test_caller_that_changes_the_returned_member_*`, `test_target_that_only_compares_*`).
- Demo rows in `fixtures/demo_catalog_entries.py`: `class-a-catalog-argument-target-returns-key`,
  `class-a-catalog-argument-target-subscript-store`, `class-a-catalog-argument-target-comparison`.
  The shop target `read_option` now returns `_OPTION_VALUES[key]`, so the clean demo stays PASS.
