# Known limits

Archkeel decides from one static observation of Python source. This page lists what that
observation cannot see or only sees partly, with the measured size where one exists. A limit here
is a reason for review, not a failed check.

## Calls are partly resolved

The import graph is complete; the call graph is not. Call records feed the `calls_unresolved`
and `unresolved_ratio` regression checks, never a rule.

| Repository | Unresolved | Partially resolved | Analyzed |
|---|---:|---:|---:|
| Archkeel (`fixtures/D-self`) | 428 (8.7%) | 535 | 4,908 |
| Internal 13-component service (`docs/evidence/internal-service/`) | 998 (23.1%) | 380 | 4,318 |

The resolver follows indexed names, import aliases, builtins and simple attribute chains. Since
AD-37 it also follows a receiver whose type a literal or an annotation makes statically obvious,
against a hand-written table of `list`/`dict`/`set`/`frozenset`/`tuple`/`str`/`Path` methods; a
literal-typed receiver resolves, an annotated one only `partially_resolved`, because Python never
checks an annotation at runtime. Since AD-40 a call result is typed too, but only from a closed
table of documented library types: a constructor the import binding names (`hashlib.sha256()`,
`argparse.ArgumentParser(...)`, Rich's `Console(...)` and `Table(...)`, `Path(...)`) and a method
whose documented return is in that table (`add_subparsers`, `add_parser`, `relative_to`); such a
receiver is `partially_resolved`, never `resolved`. It does not read return annotations in the
analysed source or follow a value across a conditional reassignment, so a call on a project
call result (`Repository(root).save(...)`), a receiver two attributes deep (`self.items.append`)
and an attribute of an awaited value stay unresolved. An unresolved call is not proven dynamic
at runtime.

## A facade type position is not always decidable

`boundary_types` reads one annotation string per parameter and return of a declared facade
function. It decides a builtin, a bare `dict`/`object`, a bare name its module's import bindings or
own class definitions resolve, and a known collection (`list`, `tuple`, `set`, `frozenset`,
`Sequence`, `Iterable`, `Iterator`, `Collection`, `AbstractSet`) holding such a name, one level in.
It cannot decide a dotted name, a mapping, a nested subscript, a union, a forward-reference string,
a missing annotation or a type owned by no declared component. Since AD-67 the undecided part is
reported rather than silent: each rule files one `boundary_type_limit` record in `unknowns` naming
the positions it saw, the positions it decided and a count per undecidable kind. The record reports
and never gates: it does not move `coverage.rules`, the diagnostics or the exit code. It does move
`declared_rules`, the reported verdict a run's rules earned: a violation-free observation reads
UNKNOWN there, not PASS, if an undecided position's reason is a real checker limit (a missing
annotation, a union, a dotted name and the like), but stays PASS when every undecided position is a
type owned by no declared component (`external_type`), since that question never applied to begin
with. A `public_api` entry the scan could not settle (`api_surface_limit`) moves it the same way,
for the same reason: the contract declared something and nothing could decide it.

A package or module facade may re-export a function. The analyzer follows the recorded
re-export chain to the definition, but keeps the declared facade as the violation subject. Alias
paths to one exact origin are decidable; distinct possible origins are reported as
`ambiguous_facade` UNKNOWN. For a declared request or result class it reads direct field
annotations once. A second model level, an ambiguous binding or an unresolved field is reported
as UNKNOWN; the analyzer does not grow a recursive type resolver.

Measured on Archkeel's own facades with the rule widened to the whole `archkeel` namespace, 88
declared facade functions carry 258 positions:

| Outcome | Positions |
|---|---:|
| Decided: a violation | 39 |
| Decided: a pass (79 builtin, 102 a declared type, directly or in a collection) | 181 |
| Undecidable: a union | 18 |
| Undecidable: a type owned by no declared component | 10 |
| Undecidable: a nested or otherwise unentered subscript | 9 |
| Undecidable: a bare name nothing resolves | 1 |

A dotted name, a forward-reference string and an unannotated position are all decidable kinds of
undecidable; Archkeel's own facades happen to contain none. What a builtin is comes from
`dir(builtins)` on the analyzer's own interpreter, so it is that Python build's answer, not a list
kept by hand.

## Imports and constructs

- Dynamic imports such as `importlib.import_module(name)` add no dependency edge. Forbid them with
  the `dynamic_import` construct where boundaries must hold.
- Private cross-package imports remain confirmed crossings. A private attribute rooted in an
  untyped, unresolved, or top-level `Any` parameter is recorded as
  `private_attribute_access_limit` UNKNOWN and counted in `untyped_private_accesses`; nested
  `Any` keeps the outer annotation owner, and the static scan cannot prove runtime ownership
  beyond that type.
  Typed parameters, locals and public attributes are excluded. `import pkg` followed by
  `pkg._member` remains outside this signal unless the expression is rooted in such a parameter.
- `forbidden_construct` matches names as written; aliases and shadowed names are blind spots (AD-8).
- `string_literal_compare` follows only a single, statically proven module/class binding to a
  `str` literal. Imported, conditional, dynamic or reassigned names stay unknown; Enum members,
  named constant sets (`x in NAMES`), dict-literal membership, `str.startswith` and dispatch
  tables remain outside the construct. A Python dunder, driver string, trust-boundary parser and
  value already typed as a `Literal` are still reported like any other (AD-80).
  `object.__setattr__(...)` is not `setattr` (AD-48).
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
