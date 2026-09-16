# Architecture rules

Contract 2.0 separates deterministic rules, regression checks, declarations and review claims.

| Class | Purpose | Check outcome |
|---|---|---|
| A | Enforce a fact visible in one complete observation. | PASS or FAIL |
| B | Compare accepted and candidate observations. | PASS or FAIL |
| C | Preserve review context without enforcement. | Not evaluated |
| D | Record a bounded human or LLM review claim. | HYPOTHESIS |

## Class A: deterministic rules

`closed_world` is an implicit Contract 2.1 invariant (AD-15): each ordered component pair is a
decision, made exactly once, by one `allowed_dependency` rule or one `forbidden_dependency` rule.
Being observed is not a decision; an undecided pair is reported as `decision.open`, naming whether
it is observed and at how many import sites. A pair decided twice, or decided both ways, is
`closed_world.duplicate`; an observed pair also forbidden is `closed_world.observed_forbidden`. A
complete scan and exact package assignment make the result deterministic; dynamic imports remain a
blind spot. Removing one pair rule from Archkeel is an example violation.

`forbidden_dependency` fields are `source`, `target`, `include_type_checking`, optional
`target_symbol` and optional `allowed_sources`. The analyzer matches import records by exact module
prefix, except when `source` and `target` each name a declared component package exactly and
`target_symbol` is absent: that rule decides the whole component pair (AD-15), so it also enforces
every package of the source component against every package of the target, not only the named
ones. `allowed_sources` lists exact source modules, unlike the prefix scopes of
`forbidden_construct` and `external_dependency_scope`. Closed-world validation counts every
observed import, including `TYPE_CHECKING` and allowed-source imports, so `allowed_sources` and
`include_type_checking: false` only fit a rule scoped below a component pair, such as a submodule
target or a `target_symbol`. A complete scan, fixed source bytes, analyzer digest and Python
version make the result deterministic. Unresolved dynamic imports remain a blind spot. Importing
`sample.cli` from `sample.core` is an example violation.

`allowed_dependency` fields are `source`, `target` and `rationale`: the architect's decision that a
component pair may depend, recorded with its reason. It adds no report violation and is evaluated
only by closed-world validation, never by the analyzer. Declaring `sample.core` allowed to depend
on `sample.cli` when no code observes that edge is valid; it simply decides the pair.

`forbidden_construct` fields are `source`, `constructs` and optional `allowed_sources`, whose
prefixes exempt owners as in `external_dependency_scope`. Supported constructs are `getattr`,
`hasattr`, `cast`, `eval`, `exec`, `dynamic_import`, `type_ignore`, `any_annotation`, `assert` and
`broad_except`. It matches typing-signal records from direct AST calls, type-ignore comments and
`Any` in a parameter, return or variable annotation, and construct records from `assert` statements
and `except` handlers with no type or with `Exception` or `BaseException`, alone, in a tuple or as
`builtins.Exception`; `except Exception: raise` counts. One record is one violation, so an
annotation repeated across a serialisation boundary reports once per position. Fixed source bytes,
analyzer digest and Python version make the result deterministic. Aliasing first, such as
`f = getattr; f(value, name)` or `E = Exception; except E:`, is not resolved and remains a blind
spot. Calling `eval()` below the configured source is an example violation.

`external_dependency_scope` fields are `dependency` (a top-level import name) and
`allowed_sources`. It matches import records whose target is the dependency or one of its
submodules, including `TYPE_CHECKING` imports. Fixed source bytes and analyzer digest make the
result deterministic. Imports through `importlib` remain a blind spot. Importing `rich` from
`archkeel.check` when only `archkeel.cli` is allowed is an example violation.

`complete_assignment` has the field `source`. Every scanned module below `source` must belong to
exactly one component; a module matched by two different components counts as unowned, while
one component may list nested packages. The `source` module itself
and blank files are exempt because they hold no code a component could own. A complete scan
makes the result deterministic. A module whose first line is blank but contains code has no source
excerpt, so its violation cannot be traced and the run reports UNKNOWN (exit 2) instead of FAIL.
Adding `archkeel/extra.py` without a component package is an example violation.

`no_component_cycles` has no selector fields. It projects import records, including
`TYPE_CHECKING` imports, onto components and reports each strongly connected component with two or
more members. A complete scan and exact package assignment make the result deterministic. Imports
between unowned modules are invisible; combine it with `complete_assignment`. Importing
`sample.cli` from `sample.core` while `sample.cli` imports `sample.core` is an example violation.

`interface_boundary` has the optional field `include_type_checking` (default `true`) and no
selector fields; it applies wherever a component declares `public`. A component's `public` list
holds `pkg.module` entries, which make every non-underscore name of that module public, or its
`__all__` when the module declares one, and `pkg.module:Name` entries, which make exactly one name
public. It matches every cross-component import whose target component declares `public` and
reports a violation unless the imported name, directly or through its re-export chain, resolves to
a declared name; underscore names never qualify. An import a `forbidden_dependency` rule already
rejects is reported once, as that violation, and never also as `interface_boundary` (AD-18). A
complete scan, fixed source bytes and analyzer digest make the result deterministic. An empty
`__all__` reads the same as no `__all__` at all,
aliasing during a re-export is not resolved, and `from pkg import submodule` is matched as the
name `pkg:submodule` rather than the module `pkg.submodule`; these remain blind spots.
Importing `sample.core.impl`
directly from `sample.cli` when `core` declares only `sample.core` as public is an example
violation.

`sibling_isolation` has the field `members`, at least two dotted prefixes, and the optional
`include_type_checking` (default `true`). Peers reach shared modules and are reached from outside,
but never each other: the analyzer reports every import whose source and target lie in two
different members. One rule replaces the n*(n-1) `forbidden_dependency` rules the same intent would
otherwise need, and it stays inside a component, where no component pair decision applies. A
complete scan and fixed source bytes make the result deterministic; dynamic imports remain a blind
spot. Archkeel applies it to the eight analyzer collectors (AD-1, AD-25). Importing
`sample.core.first` from `sample.core.second` when both are members is an example violation.

## Class B: regression checks

Regression checks compare accepted and candidate observations. They include scalar counts,
integer cross-multiplied ratios and semantic fingerprints.

- **Measurement:** `calls_unresolved`, `unresolved_ratio`, typing positions, cycles, private
  crossings, violations and coverage failures.
- **Determinism:** both observations must use comparable Python and analyzer versions.
- **Blind spots:** a stable count can hide replacement of one finding by another; fingerprints
  cover supported semantic changes, not intent.
- **Example:** reject a candidate whose unresolved call count rises from 0 to 1.

`coverage_failures` is measured but cannot regress between two comparable observations: an
incomplete scan produces no measurements, so the check reports NOT CHECKED instead.

## Class C: declarations

Fields under `declarations` preserve capabilities, review scopes, public interfaces, commands,
context roots, paths and owners. Archkeel decodes and reports them but does not enforce them.
`public_api` is superseded by the component `public` field and its `interface_boundary` rule
(AD-9); it stays valid but new contracts should declare `public` per component instead.

- **Measurement:** none; declaration records mirror the contract.
- **Determinism:** decoding is deterministic for a valid Contract 2.0 document.
- **Blind spots:** Archkeel makes no claim that code follows a declaration.
- **Example:** record `sample.api` as the intended public interface.

A class-C entry records a judgment: a responsibility, an intended interface, a path or an owner
that a person decided. Archkeel stores and reports it verbatim and never evaluates it, so it can
neither pass nor fail a check. A judgment that needs testing becomes a class-D claim bound to an
evidence digest, and its outcome stays HYPOTHESIS, never PASS or FAIL. A judgment that reduces to
a fact visible in one observation belongs in class A instead.

## Class D: review claims

Class D names what one observation suggests and a person decides. A claim is a triple: a signal the
analyzer records, a pure derivation in `ir`, and a report section without a verdict (AD-26). A claim
whose signal is missing reports UNKNOWN and lists nothing, so an analyzer that cannot produce the
signal costs the other claims nothing.

`unreferenced symbol` is the first claim. Its signal is the `references` section, which records
every use of a scanned symbol that is not a call: a function put into a table, passed as an
argument, or read as a property. The derivation names each symbol that no call, reference or import
inside the scan scope mentions, after setting aside dunder names, `__all__` entries and methods of a
subclass, which the runtime dispatches without naming them.

- **Measurement:** candidates, symbols examined, symbols set aside, and the unresolved-call share
  beside them.
- **Determinism:** the candidate list is deterministic for one observation; whether a candidate is
  truly dead is not, and never becomes a verdict or an exit code.
- **Blind spots:** a consumer outside the scan scope, such as a test, is invisible; so is a name
  reached through a string, a registry or a plugin entry point.
- **Example:** on Archkeel itself the signal removed four of six candidates that a call graph alone
  had reported, and the remainder are public API used only by tests.

## Migrating from 1.1.0

Contract 2.0 keeps `components` and `rules` at the top level. Move every class-C declaration
under the optional `declarations` object:

| Contract 1.1.0 field | Contract 2.0.0 field |
|---|---|
| `capabilities` | `declarations.capabilities` |
| `review_scopes` | `declarations.review_scopes` |
| `public_api` | `declarations.public_api` |
| `public_api_provenance` | `declarations.public_api_provenance` |
| `public_commands` | `declarations.public_commands` |
| `context_roots` | `declarations.context_roots` |
| `context_roots_provenance` | `declarations.context_roots_provenance` |
| `paths` | `declarations.paths` |
| `spot_owners` | `declarations.spot_owners` |

Set `schema_version` to `2.1.0`. The optional `$schema` points to
`schema/architecture-contract.schema.json`. Omit unused declaration arrays instead of copying
empty arrays. Decide every ordered component pair with an `allowed_dependency` or
`forbidden_dependency` rule (AD-15); `validate --root . --json` reports an undecided pair as
`decision.open`. Run `archkeel validate --root . --json` to verify the migrated contract.
