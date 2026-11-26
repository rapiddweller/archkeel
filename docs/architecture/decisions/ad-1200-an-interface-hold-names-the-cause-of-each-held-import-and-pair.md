# AD-1200 An interface hold names the cause of each held import and pair

**Status.** Accepted. Builds on AD-504, AD-604 and AD-484. Part of #2086, #1963 and #1919.

**Decision.** The `explain.holds.rules[RULE]` entry of an `interface_boundary` rule that is UNKNOWN now says why.

1. Held imports. The kind is `interface_imports`. `interface.classes` counts the held imports of each
   missing fact (`gap`) and cause class (`class`). `interface.imports` lists the first 20 with their
   source, target, name, evidence ids and the cause that the collector states (`cause`, or null).
2. Held pairs. The `pairs` of the rule have an `origin`, and `origins` counts the pairs of each
   origin: `dispatch`, `not_execution_only`, `unowned_end`, `unobserved_module` or `named_site`.

The Python collector states the cause when it withholds a route. The cause is a word of the closed
vocabulary `RouteWithheld` (`ambiguous_reexport`, `uncertain_hop`, `unread_all`, `outside_write`,
`escaped`, `type_checking_reexport`) in the live field `ImportData.route_withheld`, with the hop or
the module that it names in `route_withheld_at`. Neither is on the wire. A cause that the collector
does not state is `not_stated`. In the frame, `cause` is `{kind, at}`. The cause decides nothing:
the route is withheld in the same cases as before and no verdict changes. The core and the report
project the typed value. The shell decodes it (`core_explain.py`) and holds no rule.

The values are plain: no new type derives a serializer, because each such type adds a "trait impl
may run" gap to every module that reaches it (the self-check grew by 532 items with the first
design and by 38 with this one). The frame values are `serde_json` values built by two small
functions; the model types sit in the existing `causes.rs`.

**Measured** on EE `560d5c7ef` and CE `23bd48d9` (copies), and on the self-check, at the base of this change:

| Scan | Held | Class |
|---|---|---|
| EE | 2,509 imports in 20 rules | `escaped` (publication route) |
| EE | 16 / 13 / 6 / 4 | `escaped` (type publication) / `outside_write` / `not_stated` / `type_checking_reexport` |
| CE | 465 imports in 7 rules; 2 for the type route | `escaped` |
| Self-check, `NATIVE-INTERFACE-BOUNDARY` | 884 pairs / 327 pairs | `dispatch` / `named_site` |

**Reason.** A hold named the import but not why its route was withheld, so nobody could act on it.

**Limit.** `escaped` names the module, not the use that hands its object on; recording that site is
the next step (#2117). This change does not shrink a hold. A cause that is a gap of the collector can be closed
only with its own proof, in its own change.

**Tests.** `routes_tests.rs` has a plant for each cause. `causes_tests.rs` covers the classes and the
origins. `test_cli_fixture_matrix.py` checks the frame of the planted open route.
