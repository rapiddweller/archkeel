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

`report --only calls --json` lists every unresolved and partially resolved call with its reason
and owning component. A change in unresolved calls is named by file, caller and expression, not
by line (AD-100). A renamed caller reads as one removed and one added call, a renamed or moved
file as all of its calls removed and added, and of two identical calls in one caller the new one
cannot be told apart: the row names both lines. `validate --against` names no site for a call
in a new file that is git-ignored, inside a submodule, or marked `export-ignore` by the
`--against` revision: its archive never holds such a file, and `unresolved_call_note` says so. A
file the revision's snapshot already holds is always compared. With `--root` below the Git top
level the revision cannot be archived, and a file name under the scan roots that is not UTF-8
leaves Git's listing unreadable; either way the field stays `null`, with a note.

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
for the same reason: the contract declared something and nothing could decide it. Since AD-92 every
other `unknowns` kind does too, except the standing disclaimers `dynamic_call_limit`,
`context_alias_limit` and `private_attribute_access_limit`, and the same count is the
`unknown_positions` scalar.

A package or module facade may re-export a function. The analyzer follows the recorded
re-export chain to the definition, but keeps the declared facade as the violation subject. Alias
paths to one exact origin are decidable; distinct possible origins are reported as
`ambiguous_facade` UNKNOWN. For an owned declared request or result class, it recursively checks
declared fields and known collection or union members. A repeated class on the current path ends
that branch. Ambiguous bindings, unresolved names and unsupported annotation shapes stay UNKNOWN;
their records include the signature-rooted field path and the nested annotation.

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

## Dart profile

`[scan] language = "dart"` reads directive headers only, never declarations or bodies (AD-97).
What it cannot see is UNKNOWN or refused, never PASS:

| Case | Result |
|---|---|
| `interface_boundary` on an import without `show` whose module is not `public`, when a `module:name` entry or an `export` of that library could make a used name public | UNKNOWN (`interface_symbol_limit`) |
| `forbidden_dependency` with `target_symbol` on an import without `show` | UNKNOWN (`dependency_symbol_limit`) |
| a `declarations.public_api` `module:name` entry on a scanned library | UNKNOWN (`api_surface_limit`) |
| `symbol_placement`, `boundary_types`, `forbidden_construct` | exit 2, `rule_unsupported_by_profile` |
| `declarations.context_roots`, a budget on `typing_positions`, `calls_unresolved`, `private_crossings` or `untyped_private_accesses` | exit 2, `rule_unsupported_by_profile` |
| those four scalars | `null`, compared as `n/a` |
| `unreferenced_symbols`, `unread_bindings`, `type_fanin`, `repeated_logic` | UNKNOWN: `symbols`, `references` and `bindings` are null |

Own imports are exactly `package:<namespace>/...` and relative URIs; `package_config.json` is not
read. Every alternative of a conditional import is an edge. `init` does not detect a Dart package.

The edges were compared with the official parser on a real Flutter repository. A script outside
this repository listed every directive with `package:analyzer` 14.4.0 (`parseString`, Dart SDK
3.13.4) and resolved relative and `package:<name>/` URIs to files under `lib/`. Its list was
diffed with the import records of `archkeel report` by library, directive line, kind, target,
prefix and `show` names.

| [flutter/samples](https://github.com/flutter/samples) at `8a4cf1db16d52741f0e59e1bfe818723430c35bc` | Libraries | Import and export edges | Differences |
|---|---:|---:|---|
| `compass_app/app` (data, domain, ui layers) | 89 | 433 | none |
| all 35 packages with a `lib/` | 312 | 1,183 | none |

`part` directives (22 in `compass_app`, 64 in all) are no edge by design: a part belongs to the
library that lists it, so the profile records its directives as that library's, and no part file
is a module. No package there has a conditional or deferred import; `fixtures/G-dart` and its
tests cover those.

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
