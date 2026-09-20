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
ones. `allowed_sources` here lists exact source modules; `forbidden_construct` and
`external_dependency_scope` match their `allowed_sources` by prefix and take exact names as
`exact_sources` (AD-49). Closed-world validation counts every
observed import, including `TYPE_CHECKING` and allowed-source imports, so `allowed_sources` and
`include_type_checking: false` only fit a rule scoped below a component pair, such as a submodule
target or a `target_symbol`. A complete scan, fixed source bytes, analyzer digest and Python
version make the result deterministic. Unresolved dynamic imports remain a blind spot. Importing
`sample.cli` from `sample.core` is an example violation.

`allowed_dependency` fields are `source`, `target` and `rationale`: the architect's decision that a
component pair may depend, recorded with its reason. It adds no report violation and is evaluated
only by closed-world validation, never by the analyzer. Declaring `sample.core` allowed to depend
on `sample.cli` when no code observes that edge is valid; it simply decides the pair.

`forbidden_construct` fields are `source`, `constructs` and optional `allowed_sources` and
`exact_sources`, which exempt owners the way `external_dependency_scope` exempts modules. An
owner is the qualified scope a construct is written in, a module, class or function such as
`sample.cli.main`; an `allowed_sources` prefix exempts it and every scope nested in it, an
`exact_sources` entry only the scope it names (AD-49). The shop sample exempts exactly
`shop.cli.main.main` from its broad-except rule, and the demo rows `class-a-broad-except-exact`
and `class-a-broad-except-prefix` run one nested handler under each list: reported, then allowed.
Supported constructs are `getattr`,
`hasattr`, `cast`, `eval`, `exec`, `dynamic_import`, `type_ignore`, `any_annotation`,
`placeholder_body`, `assert`, `broad_except`, `setattr`, `delattr`, `vars`, `dunder_dict` and
`string_literal_compare`. `placeholder_body` covers a function body that is
only `pass`, `...` or a lone `raise NotImplementedError`, and exempts a method carrying
`@abstractmethod` or `@overload` and a method of a class that has a base, where emptiness is the
interface rather than a missing implementation (AD-29). `setattr`, `delattr` and `vars` are calls
written bare or as `builtins.<name>`, and `dunder_dict` is any `x.__dict__` access.
`string_literal_compare` is a comparison where `==` or `!=` has a `str` literal on one side, an
`in` or `not in` test against a non-empty tuple, list or set literal of `str` literals only, or a
`match` statement with a `str` literal value pattern in any case, wherever it stands; it counts
once per comparison and once per `match` statement, and `if __name__ == "__main__":` is not
counted. It is syntactic, so whether a compared value is a closed vocabulary is decided by
`source` and `allowed_sources` (AD-48). It matches
typing-signal records from direct AST calls, type-ignore comments and
`Any` in a parameter, return or variable annotation, and construct records from `assert` statements,
`except` handlers with no type or with `Exception` or `BaseException`, alone, in a tuple or as
`builtins.Exception` (`except Exception: raise` counts), empty bodies, and the reflection and
string-literal forms above. One record is one violation, so an
annotation repeated across a serialisation boundary reports once per position. Fixed source bytes,
analyzer digest and Python version make the result deterministic. Aliasing first, such as
`f = getattr; f(value, name)` or `E = Exception; except E:`, is not resolved and remains a blind
spot. Calling `eval()` below the configured source is an example violation.

`complete_external_scope` fields are `source` and `rationale`. Every import below `source` whose
target is neither a scanned module nor part of the standard library must be covered by an
`external_dependency_scope` rule; an import no rule names is a violation naming the importing
module. It closes for dependencies what `complete_assignment` closes for modules, so a package the
contract never mentions — including one that does not exist anywhere — stops passing silently
(AD-28). The standard library is read from the analyzer's own Python version, which the
observation records, so a version change can move a module into or out of the exempt set.
Relative imports are internal by construction and are never counted. A dependency only the
package root imports is covered by a rule whose `exact_sources` names that root, so covering it
does not allow it in every module below (AD-49). Importing `helpers` with no rule naming it is
an example violation.

`complete_requires` has no selector fields. Every import that crosses from one component to another
must be covered by a `requires` entry of the importing component, and an import no entry covers is a
violation naming the importing module. An entry may list `through`, module prefixes of the required
component; then only an import of one of those modules is covered, and an import of any other
module of that component is the same violation (AD-42). An entry may also record `decided_by`,
`architect` or `agent`, which overrides the component's own; who decided an edge changes no
evaluation and is counted by `agent_decisions` (AD-50). A `through` prefix that names no module
in the scan is a `reference.namespace` diagnostic in `validate`; one that names a module of a
different component covers nothing. A component pair absent from the list is decided, not open:
absence forbids, the way `complete_assignment` makes an unassigned module a violation rather than a
question (AD-32). `TYPE_CHECKING` imports count unless `include_type_checking` is false. Without the
rule nothing changes, so a contract that never adopts it keeps deciding pairs one by one. A
`requires` entry naming a component that does not exist covers nothing and remains a blind spot. A
`render` component that imports `model` without requiring it is an example violation. The same
rule kind is evaluated a second time against a component's declared inside, over the imports the
outer scan already collected, so a crossing between two sub-components that no `requires` entry
covers is a violation of the inside's own rule (AD-34). An inside's rules are recorded under the
component holding them, as `<component>:<rule id>`, and its violations name them there, so the
finding reads `store:STORE-REQUIRES-COMPLETE` rather than the bare id the inside contract wrote
(AD-36). The same prefix keeps the two levels apart: a `complete_requires` an inside declares
decides that level's pairs, never the pairs above it.

`external_dependency_scope` fields are `dependency` (a top-level import name), `allowed_sources`
and `exact_sources`, at least one of the two non-empty. It matches import records whose target is
the dependency or one of its submodules, including `TYPE_CHECKING` imports, and allows those whose
source module falls under an `allowed_sources` prefix or equals an `exact_sources` entry. A
package root is a prefix of every module in its package, so only `exact_sources: ["sample"]`
allows `sample/__init__.py` a dependency that `sample.core` may not import (AD-49). Fixed source
bytes and analyzer digest make the result deterministic. Imports through `importlib` remain a
blind spot. Importing `rich` from `archkeel.check` when only `archkeel.cli` is allowed is an
example violation.

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
selector fields; it applies wherever a component declares `public`. A component's optional
`decided_by` records who decided that list, and defaults every `requires` entry that records
none; `agent_decisions` counts one declared `public` list, empty or not, as one decision, and a
component that declares no `public` at all recorded no interface decision (AD-50). A
component's `public` list
holds `pkg.module` entries, which make every non-underscore name of that module public, or its
`__all__` when the module declares one, and `pkg.module:Name` entries, which make exactly one name
public. It matches every cross-component import whose target component declares `public` and
reports a violation unless the imported name, directly or through its re-export chain, resolves to
a declared name; underscore names never qualify. An import a `forbidden_dependency` rule already
rejects is reported once, as that violation, and never also as `interface_boundary` (AD-18). A
complete scan, fixed source bytes and analyzer digest make the result deterministic. An empty
`__all__` reads the same as no `__all__` at all, and aliasing during a re-export is not resolved;
these remain blind spots. `from pkg import name` is matched as the module `pkg.name` whenever the
scan holds that module, exactly like `import pkg.name`, and as the name `pkg:name` only otherwise.
So when the scan holds `pkg.submodule`, `from pkg import submodule` passes a `pkg.submodule` entry,
not a `pkg:submodule` entry. That also holds when the package already exposes an attribute with
that name: Python may then bind the attribute instead of importing the submodule, and the result can
depend on whether the submodule was imported before. Archkeel does not model that runtime state
([#23](https://github.com/rapiddweller/archkeel/issues/23)). `validate`
reports such a name entry as `interface.unused` without pointing at the module entry that would
admit the import; only the violation beside it names `pkg.submodule`. Importing `sample.core.impl`
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

Every command that derives a claim also names it: `report` and `validate` print the counts in the
terminal and carry them under `claims` in `--json`, where a missing signal is `null` rather than
zero, while the HTML report lists the candidates themselves (AD-35). None of this reaches an exit
code.

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
  reached through a string, a registry or a plugin entry point. The resolver limits in
  `known-limits.md` reach the claim as false candidates: a method invoked on a call result, as in
  `Repository(root).save(...)`, names nothing the claim can see. That is why the unresolved-call
  share is printed beside the candidates — it is the size of that blind spot.
- **Example:** on Archkeel itself the signal removed four of six candidates that a call graph alone
  had reported, and the remainder are public API used only by tests.

`unread binding` is the second claim. Its signal is the `bindings` section, which records every
parameter or local that no expression in its own function reads. Nothing is resolved across
modules, so the claim is supported wherever the analyzer ran. It sets aside a name with a leading
underscore, which is Python's own mark for a deliberately unused binding, `self` and `cls`, and
the parameters of a method that overrides another or fills an empty stub, because something other
than the body chose them.

- **Measurement:** candidates, and the functions examined beside them. The bindings set aside are
  not counted, because the signal records only what it names.
- **Determinism:** the candidate list is deterministic for one observation; it never becomes a
  verdict or an exit code.
- **Blind spots:** a name bound by an import inside the function, by `except ... as` or by a
  `match` pattern is not recorded, and a read through `locals()` is invisible.
- **Example:** on Archkeel itself the claim names nothing, because `ARG` and `RUF059` already
  reject such a binding at lint time; the demo tour carries one unread parameter and one
  unread local.

`repeated logic` is the third claim, and the only one that reads a class-C declaration. Its signal
is the `shape` each function and method symbol carries: the node types of the body in walk order,
hashed, with names, literal values and the docstring left out, so a renamed or re-documented copy
still matches its original. The derivation groups functions by shape and, for every declared
`spot_owner`, names each function outside the owner whose shape matches one inside it.

- **Measurement:** candidates, the declared owners examined, and the functions compared.
- **Determinism:** the shape is an exact digest, not a similarity score, so the candidate list is
  the same on every machine; it never becomes a verdict or an exit code.
- **Blind spots:** a copy that changed one operator or split a loop has a different shape and is
  invisible. Only exact structural twins of at least ten nodes count, a floor measured so that
  shapes the language forces — `ast.NodeVisitor` demanding two visit methods, an empty `Protocol`
  method — are not reported as repetition (AD-30).
- **Example:** the shop tour copies `Order.total` into `shop.app`, which the claim names against
  the declared owner `shop.model`; without a declared `spot_owner` the claim reports nothing,
  because no architect decided anything for it to contradict.

`component larger than its level` is the fourth claim, and the only one that measures the contract
against itself. Its signals are the `modules` and `dependency_edges` sections, the same ones the
size table reads, and the derivation reuses that table rather than counting a second time. A
component is named when it holds more modules than the contract has components, or more edges among
its own modules than the contract has edges between components. Where the component declares no
inside, no decision is owed there (AD-24), so silence could mean small or merely unexamined; the
claim removes that ambiguity without turning it into a verdict.

- **Measurement:** the components named, beside the top level's own component and edge counts, so
  a reader can check every comparison.
- **Determinism:** both quantities come from one observation and one derivation, so the claim and
  the size table can never disagree; it never becomes a verdict or an exit code.
- **Blind spots:** the claim measures what a component holds, not how tangled it is — a component
  of many independent modules is named alongside one that is genuinely knotted. It says nothing
  about what a second level would find, because that needs a second scan at a narrower scope,
  which one observation cannot supply (AD-10); an inside a component has already declared is a
  different matter, recorded, judged and drawn from this same observation (AD-34). Missing either signal reports UNKNOWN, because a
  comparison against zero component edges would name every component.
- **Example:** on Archkeel itself the top level holds 6 components and 8 edges, and the claim names
  `analyzer` (21 modules, 47 inner edges), `check` (13 and 23) and `ir` (15 and 22), while `cli`,
  `render` and `host` stay below on both. Opening a level for one of them is `archkeel init
  --source <path> --namespace <package>`, which drafts that inside as a contract of its own (AD-20).

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
