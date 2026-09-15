# Known limits

Archkeel decides from one static observation of Python source. This page lists what that
observation cannot see or only sees partly, with the measured size where one exists. A limit here
is a reason for review, not a failed check.

## Calls are partly resolved

The import graph is complete; the call graph is not. Call records feed the `calls_unresolved`
and `unresolved_ratio` regression checks, never a rule.

| Repository | Unresolved | Partially resolved | Analyzed |
|---|---:|---:|---:|
| Archkeel (`fixtures/D-self`) | 630 (19.1%) | 257 | 3,303 |
| Internal 13-component service (`docs/evidence/internal-service/`) | 998 (23.1%) | 380 | 4,318 |

The resolver follows indexed names, import aliases, builtins and simple attribute chains. It does
not use annotations, local assignments or return types, so `x.method()` on a parameter, a call on
a call result and an attribute of an awaited value stay unresolved. An unresolved call is not
proven dynamic at runtime.

## Imports and constructs

- Dynamic imports such as `importlib.import_module(name)` add no dependency edge. Forbid them with
  the `dynamic_import` construct where boundaries must hold.
- Only import records cross boundaries: `import pkg` followed by `pkg._member` is not a private
  crossing.
- `forbidden_construct` matches names as written; aliases and shadowed names are blind spots (AD-8).
- Imports under `TYPE_CHECKING` are graph edges for cycle detection even when a rule sets
  `include_type_checking` to false; the flag only affects rule violations.

## Components and packages

- `package_dependency` records name packages by their first two dotted segments. Component
  decisions and dependency rules use module-level edges and are not affected; the package records
  are coarse below that depth.
- A package's `__init__` module belongs to the component that owns the package, so a component
  cannot own `pkg/__init__.py` without also owning every subpackage. `complete_assignment` reports
  the unowned module.

## What static observation cannot decide

- Runtime behavior, data flow, performance and scalability are not observed. They belong in the
  rationale of a decision and in review.
- A rationale is checked for presence and form, not for truth.
- Precommitment proves that an expectation was published before submission, not that no private
  edit came first.
- The analyzer must run on at least the target repository's Python; otherwise the result is
  `runtime_mismatch`.
- Determinism is measured for one machine and Python build (AD-7), not across Python versions or
  operating systems.
