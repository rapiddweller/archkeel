# AD-83: Private attribute access without owner evidence is UNKNOWN

## Decision

Keep confirmed `private_crossings` for private cross-package imports. Also measure private
attribute expressions rooted in an untyped or `Any` parameter, but record them as
`private_attribute_access_limit` UNKNOWN records and count them in `untyped_private_accesses`.

The record names the function, parameter and private attribute. Typed parameters, local
values and public attributes do not qualify. The analyzer does not infer runtime ownership
from a parameter name, an annotation alone or an unproven call graph.

`private_crossings` counts confirmed imports only. The separate scalar and `unknowns` dimension
expose the measured risk without turning uncertainty into a crossing or violation.

## Evidence

Issue #88 showed `context.root._registry` crossing a component boundary without an import.
The AST proves the private expression and missing/`Any` annotation, but not the runtime
component owning `context`.

Check: `tests/test_private_crossings.py`, the interface demo and the private-crossing check
variants in `fixtures/demo_catalog_interfaces.py` and
`fixtures/demo_catalog_check_regressions.py`.

`ANALYZER_VERSION` rises to 0.33.0 because the observation gains a new UNKNOWN record.
