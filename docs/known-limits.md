# Known limits

Archkeel checks one static source snapshot. Python, Dart and TypeScript observe different
evidence; missing proof stays UNKNOWN or unavailable. A listed limit calls for review.

## Report layout is not architecture proof

Physical frames are navigation groupings, not semantic owners. Target dependencies are
declarations, not observed calls or execution order. Responsibilities are contract annotations;
the report does not prove that the code fulfills them.

The connector router tries bounded detours around headers and cards. Dense or manually moved
layouts can have no clear route: the edge remains visible with a renderer layout warning, without
changing the architecture verdict. Browser checks cover concrete regressions, not universal
collision-free routing. Fit overview can shrink labels; 100% zoom and scrolling retain detail.
Fullscreen has a browser-API path and a window fallback; headless tests do not prove every OS's
native fullscreen behavior.

## External API closure

External API closure follows one proven local base chain, including generic field substitutions
(AD-131). Multiple-base precedence, cycles, dynamic class bodies and unresolved inherited types
retain API UNKNOWN with source evidence. Compound generic arguments are not substituted.

## Analyzer deadline

The bundled analyzer has a 300-second deadline. Exceeding it returns exit 2 and
UNKNOWN with no complete observation; an older HTML file is not a fresh result.
Historical pinned CE and EE timings live in the [measurement evidence](evidence/rule-yield/README.md).
They are not current release measurements. The deadline is a bound, not a completion guarantee.
Recursive facade checks reuse re-export indexes per boundary pass (AD-119, #192).
This removes repeated import scans per function, not all scaling limits.

## Empty-crossing rule receipts

An `interface_boundary` or `complete_requires` scope receives PASS only with a
non-empty, fully covered scope and unique ownership. Missing receipts and any
other unproven non-declaration rule make both its row and aggregate
`declared_rules` UNKNOWN (#194, AD-124). A Python package initializer with no AST
statements is the sole unowned-module exception: comments and whitespace qualify;
docstrings and imports do not. Physical scope proof follows recorded module names
and file paths; an unmappable domain prevents proof (#232, #233).

## Calls are partly resolved

The import graph covers the static imports in the scanned source; dynamic imports remain a
limit below. The call graph is incomplete. Call records feed the `calls_unresolved`
and `unresolved_ratio` regression checks, never a rule.

Current self measurements live in [`fixtures/D-self/result.json`](../fixtures/D-self/result.json).
The historical internal 13-component service fixture (`docs/evidence/internal-service/`)
recorded 998 unresolved (23.1%) and 380 partially resolved calls out of 4,318 analyzed.

The resolver follows indexed names, imports, builtins and simple attribute chains.
A closed method table covers `list`, `dict`, `set`, `frozenset`, `tuple`, `str` and
`Path` receivers (AD-37). Literal-typed receivers can resolve; annotated receivers
are only `partially_resolved` because annotations do not enforce runtime types.
A second closed table types documented constructors and method results, including
`hashlib.sha256`, `ArgumentParser`, Rich `Console`/`Table`, `Path`, `add_subparsers`,
`add_parser` and `relative_to` (AD-40). These remain `partially_resolved`.

Project return annotations, conditional reassignment, `Repository(root).save(...)`,
`self.items.append` and attributes of awaited values remain unresolved.
An unresolved call does not prove dynamic runtime behavior.

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

See [`boundary_types`](rules.md#class-a-deterministic-rules) for supported annotations, field
walks, allowances and re-export rules. Checker limits remain explicit:

- Inherited methods and constructors follow a uniquely resolved local single-base
  chain, including stable aliases and supported generic substitutions (AD-145).
  Inherited fields and full MRO remain unproved. Missing/external bases, multiple
  inheritance, cycles, rebinding, deletes and control flow retain UNKNOWN. Findings keep
  source annotations and concrete `resolved_types` without changing IDs (AD-137).
- Ordinary-module re-exports require one unchanged literal `__all__` and a unique
  import binding (AD-109). Exact origin aliases are decidable; distinct origins are
  `ambiguous_facade` UNKNOWN. Missing/unscanned alias endpoints produce
  `boundary_type_route` without invented signature positions. Constants/classes
  are not facade functions; unsupported or unstable endpoints prevent proof.
- Public type routes apply only at their own component boundary. An uncertain
  export remains UNKNOWN and cannot hide another private type's violation.
- Arbitrary dotted names, unsupported generic shapes, unresolved forward references,
  missing annotations and unowned types cannot be decided. Owned request/result
  fields recurse through supported collections/unions; repeated classes end a branch.
  Nested UNKNOWN records retain the signature-rooted field path and annotation.
- `datetime.datetime` is the only imported stdlib scalar leaf (AD-132). Proven
  stdlib mappings are broad findings (AD-123); malformed mappings and unresolved
  external bindings remain UNKNOWN.
- A contained-map allowance needs one unique parameterized mapping and the whole
  signature annotation. Multiple contained maps and aliases on the route are
  unsupported. An allowed map cannot clear UNKNOWN in another member or branch.
- An exact native `object` allowance records accepted opacity and provenance,
  not static type closure (AD-135).

`boundary_type_limit` reports observed/decided positions and undecidable causes.
It changes `declared_rules`, not diagnostics, `coverage.rules` or exit status.
Real checker limits prevent PASS; positions owned by no component (`external_type`)
are exempt because the rule does not apply there. `api_surface_limit` and other
non-exempt UNKNOWN kinds likewise affect the aggregate (AD-92). Standing disclaimers
`dynamic_call_limit`, `context_alias_limit` and `private_attribute_access_limit` are
exempt. The `unknown_positions` scalar counts non-exempt uncertainty.

[AD-67's historical measurement](architecture/decisions/ad-67-an-undecidable-boundary-position-is-unknown-not-silence.md)
is not a current release count. Builtin names come from `dir(builtins)` on the
analyzer's interpreter, so their vocabulary depends on that Python build.

## A facade budget needs names it can list

Whole-module `public` names require one non-empty literal `__all__` assignment.
Mutation, starred elements, imports bound to `__all__`, repeated assignments,
missing `__all__` or `__all__ = []` leave enumeration UNKNOWN. Runtime writes via
`globals()` or `sys.modules` are unseen.

Whole-module imports, non-enumerated star imports and unnamed facade uses cannot
prove a name count. Pair budgets remain UNKNOWN unless their lower bound already
exceeds the ceiling. A name reachable through two facade modules counts once per
module; `TYPE_CHECKING` imports count. Declare literal `__all__` or `module:Name`
entries and import names explicitly (AD-99). Own whole-module facades lack
`__all__`, so the contract pins pair budgets only.

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
- Exact type-ignore allowances bind the source line, qualified scope, AST statement and comment
  tag; a line shift needs contract review. Standalone comments and statements sharing their
  first line with a sibling or compound header cannot match (AD-133).
- `string_literal_compare` follows only a single, statically proven module/class binding to a
  `str` literal. Imported, conditional, dynamic or reassigned names stay unknown; Enum members,
  named constant sets (`x in NAMES`), dict-literal membership, `str.startswith` and dispatch
  tables remain outside the construct. A Python dunder, driver string, trust-boundary parser and
  value already typed as a `Literal` are still reported like any other (AD-80).
  `object.__setattr__(...)` is not `setattr` (AD-48).
- Imports under `TYPE_CHECKING` are graph edges for cycle detection even when a rule sets
  `include_type_checking` to false; the flag only affects rule violations.

## Components and packages

- Explicit `inside` references are followed recursively. Physical folder navigation alone
  declares no boundary and proves no contract was evaluated. An invalid mount makes the
  observation incomplete; valid findings remain visible, but baseline/graph writes are refused.
- Inside contracts support components, rules and `declarations.modules`. Other nonempty
  declaration fields are refused rather than silently ignored. Keep API, compatibility,
  measurement and interface-budget declarations at the root until they have scoped evaluators
  (AD-111).
- Child `public` entries govern local sibling boundaries, not their parent's outward API
  (AD-112). Publication does not prove cohesion or a well-designed interface. With a local
  `interface_boundary`, unused-public and planned-promotion diagnostics use sibling imports
  and proven facade publication within the parent (AD-115). Unrelated scopes do not prove use;
  unknown import names do not prove non-use. Local private imports and unscanned public modules
  are checked. Inner
  `external_dependency_scope` declarations are not compared against ancestor declarations;
  ancestor rules still evaluate their own source scope.
- `package_dependency` records name packages by their first two dotted segments. Component
  decisions and dependency rules use module-level edges and are not affected; the package records
  are coarse below that depth. Declared components nested below one such package collapse into it,
  so a `package_scc` can join components the component graph keeps apart. Such a record says so:
  its `backed_by` names no module SCC and its title ends in `roll-up only`. A package SCC is backed
  when a module SCC has members in two of its packages, and then all of it reads as backed: a
  package SCC can be partly roll-up, as in `{dm, dm.domains, dm.engine}` where one module SCC
  crosses two of the packages and the third joins only through the roll-up. `backed_by` names the
  module SCC to read; it does not say every package is in it. `no_component_cycles` has no `package`
  level: its `component` level is the roll-up along declared boundaries, and its `module` level
  judges the uncollapsed graph (AD-98).
- `no_component_cycles` at `level: "module"` counts `TYPE_CHECKING` imports like the component
  level does; a cycle closed only by annotations is still reported.
- A package's `__init__` module belongs to the component that owns the package, so a component
  cannot own `pkg/__init__.py` without also owning every subpackage. `complete_assignment` reports
  the unowned module.
- `validate --against` recognises a renamed package from names, not from where the code went
  (AD-105): two packages that trade places in the same rename read as the rename the contract
  states, the way a module moved between components is a code change `--against` never judges.
  Any file left where an old prefix lived stops the rename, scanned or not, except in
  `__pycache__`. Paths are not renamed, so a moved `inside` contract remains one finding.

## TypeScript profile (0.9.0+)

The pinned compiler adapter observes imports, ownership, external dependencies, cycles and layout.
Symbols, calls, typing and private-use metrics are unavailable; unsupported rules cannot PASS.
Computed or shadowed loaders, unproved runtime aliases, missing resolver inputs and incomplete
JavaScript closure retain UNKNOWN. Analysis does not execute project code or install dependencies.
See the [adapter decision](architecture/typescript-foundation-proposal.md#evidence-and-limits)
for supported syntax and compiler-resolution limits.

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
| `declarations.facade_budgets` or `declarations.coupling_budgets`: Dart has no `__all__` and its public names are UNKNOWN (AD-99) | exit 2, `rule_unsupported_by_profile` |
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

## One run observes one scope

A run observes only its configured roots and namespace. Product results prove
nothing about an adjacent test tree. Use a second configuration for that scope
(AD-101), with these limits:

- Inside the test scope the product is an external package. `external_dependency_scope` decides
  which suites import it, by its top-level name only. A `forbidden_dependency` that targets one
  product module, such as `shop.store.sqlite` from `tests.unit`, is `reference.namespace`
  (exit 2).
- `symbol_placement` matches classes by kind, never functions. A helper function or a pytest
  fixture moved into a suite is caught only by the layout and `requires` rules, when its move
  adds a module or an import they reject. A pytest-style `class TestOrders` is a class too, so
  a suite that writes its cases as classes lists only its helper kinds in `class_kinds`, or
  allows the modules that hold such cases.
- Duplicated tests and whether a result equals its expected output are behaviour. The test
  suite and its oracle decide them, not the import graph.
- `check` compares one configuration against one accepted lock; the test scope is gated by
  `validate`.
- `report` writes to `test-artifacts/architecture/architecture.json` unless `--output` names
  another path, whatever `--config` names, so a test-scope report without its own `--output`
  replaces the product report.
- `validate --against` reads a scope's contract at the path today's configuration names, and
  never follows a rename. A contract the revision lacks, a new scope's or a moved one's, is one
  `contract introduced` widening: its old rules are not compared, and the amendment covers the
  whole contract. A baseline the revision holds at the `--baseline` path is still compared
  (AD-104).
- `--baseline` and `--amendment` are relative to `--root`, like the contract, while `report
  --output` and `check --output` stay relative to the working directory: from the repository
  root, `--root mobile` reads `--baseline known-violations.json` from `mobile/` but writes
  `--output build/architecture.json` to `build/` (AD-103). A path that resolves outside the
  root is `baseline.invalid` or `amendment.invalid`, exit 2.
- A first write into a folder inside the root that repeats the root's own name, from outside
  the root (`--root mobile --baseline mobile/x.json --write-baseline` meaning
  `mobile/mobile/x.json`), is refused as the old root-prefixed spelling. Run it from inside the
  root; once the file exists, it is read from anywhere (AD-103).

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
