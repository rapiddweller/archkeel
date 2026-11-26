# AD-1220 An escaped interface hold names the use that hands the module on

**Status.** Accepted. Builds on AD-1210. Closes #2117. Part of #2086.

**Decision.** The cause `escaped` of AD-1210 is split by the kind of the escaping use, and each
cause names the module and the first use: `<module> <- <path>:<line>`. The kinds are words of the
closed vocabulary `RouteWithheld`:

| Word | The use |
|---|---|
| `escaped_write` | writes or deletes an attribute of the module |
| `escaped_namespace` | reads the namespace of the module (`__dict__`, `__all__`, ...) |
| `escaped_child_module` | hands a child module of it on |
| `escaped_value` | hands the module object on as a value |
| `escaped_name` | hands on a name imported from the module that the survey cannot prove to be no module |
| `escaped` | an escape that the survey does not locate (a first-pass escape) |

The survey records the first use of each module in `uses.rs` (`settled_sites`). The interface hold
in the frame has `interface.places`: the ten causes that hold the most imports, each with its class,
its place and its count. The Studio shell decodes it and holds no rule.

No verdict changes: a module escapes in the same cases as before; the survey only keeps the place.

**Reason.** A team cannot judge or fix a hold without the use that causes it. Measured on EE
`560d5c7ef`: 2,525 route holds are `escaped_value` or `escaped_name`, 808 of them from one use
(`datamimic_ee/domains/registry/entities.py:52`, a name imported from `datamimic_ee.domains`).

**Limit.** An `outside_write` names the module, not the file outside the scan (#2026 names it as a gap
site). A first-pass escape that the second pass does not repeat is `escaped` without a place.

**Tests.** `routes_tests.rs` has a plant for each kind. `test_cli_fixture_matrix.py` checks `places`
in the frame of the planted open route.
