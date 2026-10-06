# AD-63 boundary_types reads a component's declared public list, not a naming convention

`boundary_types` selects functions through `component.public`, sharing
`_facade_covers` with `interface_boundary`, instead of treating every non-underscore
function as a facade. Resolve bare annotation identifiers through import bindings
or same-module classes. Accept enums, Pydantic models and types declared by their
own provider component, wherever it is.

AD-58 had rejected name resolution after 11 of 13 newly decided positions appeared
false: `ObservationResult` and `Order` belong to providers' facades, not consumers'.
Issue #44 showed the missing step was the existing public-surface lookup, not a new
resolver. `planned` still does not participate.

Self measurements changed from 610 naming-based positions (46 dict/object) to
88 declared functions carrying 258 positions (26 dict/object). The report counted
94 resolvable bare names, 74 provider-declared and 10 undeclared: six `Analyzer`/`Host`
positions in `check` and four `Summary` positions in `render`. No false positives
were found in that corpus. Keep real findings; do not exempt every dataclass or
widen rule scope across legitimate codec boundaries.

The self-contract adopted only `ANALYZER-TYPES-DECLARED`, passing for `observe`'s
declared `ObservationResult`. The measured check/render declarations had first
been reverted as `interface.unused`. [AD-65](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md)
removed that model conflict; deciding those findings remained architect work.

A component without public has no facade positions. Issue #56 reproduced false
PASS on an `api` rule inspecting zero positions. Extend `rule_subject_failures`
to use the same `_facade_positions` predicate as evaluation: no subjects means
`rule-without-subjects`, UNKNOWN. Compute the shared `exports_by_module` once for
both readers. This checks presence, not how much evidence was resolved.

Original limits: dotted names, generics, forward strings, missing annotations,
builtins and unowned types stayed silent; a later measurement reported 146/252
unresolved positions (58%). Issue #59 owned that uncertainty gap. Analyzer version
rose to 0.27.0 and D-self was regenerated.

Checks: analyzer probes cover facade selection, declared/undeclared provider types,
enums and zero-subject UNKNOWN. Boundary demos distinguish dict and declared-type
cases; self validation passed the scoped analyzer rule.
