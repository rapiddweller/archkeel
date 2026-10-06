# Architecture rules

Contract 2.0 separates deterministic rules, regression checks, declarations and review claims.

Contract 2.2 adds independent UML intent under `declarations.uml`. It uses the shared entity,
signature, visibility and relationship dataclasses. Components keep their existing owners and
permissions. Contract 2.1 remains readable with unchanged encoding. Core evaluates nested UML
intent against recorded facts; incomplete coverage retains UNKNOWN.
See [the model and current limits](architecture/uml-model-target.md).

An entity with `presence: "referenced"` can identify a foreign Target definition.
The compiler binds language, kind and qualified name to one planned declaration
across authenticated inside contracts. It keeps one compiled identity. References
carry no definition constraints; ambiguous matches and conflicting owners are errors.
An unmatched external reference stays referenced. This binding adds no source evidence.

`declarations.compat` records old module paths kept as typed compatibility shims. Each entry has
distinct `module` and `target` values and a `lifetime` (`permanent` or `migration`). A shim must
contain only imports and one literal `__all__`; every exported name must resolve only to the
target, and product modules must not import the shim. Migration entries are reported in
ArchitectureIR and HTML as remaining work. Missing evidence fails closed (AD-87).

| Class | Purpose | Check outcome |
|---|---|---|
| A | Enforce a fact visible in one complete observation. | PASS, FAIL or UNKNOWN |
| B | Compare accepted and candidate observations. | PASS or FAIL |
| C | Preserve declared context and validate public API promises. | Validation diagnostics, not a rule verdict |
| D | Record a bounded human or LLM review claim. | HYPOTHESIS |

Archkeel does not infer correctness. A position it sees but cannot resolve from deterministic
evidence stays `UNKNOWN`, with its reason measured. `PASS` means no violation was found among
the positions the rule decided; decided coverage and UNKNOWN counts remain separate (AD-90).

Each analyzer identity selects one profile in `src/archkeel/ir/profiles.py`;
unknown identities are rejected (AD-146). Profiles declare supported, partial and
unavailable rule kinds and scalars. Python supports all kinds and scalars, subject
to evidence limits. Dart and TypeScript support import-graph rules; unavailable
capabilities cannot PASS. See [profile limits](known-limits.md#dart-profile) and
[the TypeScript decision](architecture/typescript-foundation-proposal.md#evidence-and-limits).

The same symbol limits apply inside recursively mounted contracts (AD-114). Their counts cover
only the valid source scope and retain mounted rule IDs and import evidence. A complete scan
may still have an UNKNOWN rule; known violations remain visible beside undecided imports.

## Class A: deterministic rules

Complete PASS proof requires fixed source bytes, analyzer identity/runtime, complete
relevant coverage and unique ownership. Known violations survive partial coverage.
Static imports do not prove dynamic-import absence.

`complete_requires` is the compact closed-world invariant Archkeel uses itself (AD-32): each
component lists its permitted outbound component edges under `requires`, and one
`complete_requires` rule makes every absent pair forbidden. An observed crossing no entry covers
is a violation. Contracts without that rule retain AD-15's pair-by-pair form: an undecided pair is
`decision.open`, duplicate pair rules are `closed_world.duplicate`, and an observed pair also
forbidden is `closed_world.observed_forbidden`. Ownership can use recursive `packages` and exact
`exact_modules`; exactly one component must claim each observed module. Exact-involved open pairs retain every package and exact selector in the report. Archkeel does not
generate automatic rule suggestions for these pairs. An unqualified rule between uniquely declared
package endpoints still decides a mixed package/exact pair; a submodule, exact-member or
`target_symbol` rule remains partial. Exact-only pairs stay open under member rules unless an
explicit `complete_requires` policy applies.

`forbidden_dependency` fields are `source`, `target`, `include_type_checking`, optional
`target_symbol` and optional `allowed_sources`. When `source` and `target` each name a uniquely
declared component package exactly and `target_symbol` is absent, one rule decides the whole
ordered component pair (AD-15). Its ownership domain includes every package and exact module of
both components; a cross-product of redundant rules is not required. A submodule endpoint or a
`target_symbol` narrows enforcement and does not decide the whole pair. Exact-only components have
no package endpoint for this shorthand; member rules leave their pair open, while `complete_requires`
remains an explicit closed-world alternative. No exact module is promoted to a recursive package.

`allowed_sources` here lists exact source modules; `forbidden_construct` and
`external_dependency_scope` match their `allowed_sources` by prefix and take exact names as
`exact_sources` (AD-49). Pair-level `allowed_sources` or `include_type_checking: false` do not
grant an allowed component edge or exempt an observed edge from closed-world validation. A
`target_symbol` or submodule rule remains visibly partial.

`allowed_dependency` fields are `source`, `target` and `rationale`: the architect's decision that a
component pair may depend, recorded with its reason. It adds no report violation and is evaluated
only by closed-world validation, never by the analyzer. Declaring `sample.core` allowed to depend
on `sample.cli` when no code observes that edge is valid; it simply decides the pair.

`<!-- archkeel-target-graph -->` compares drawn edges with `requires` and
`allowed_dependency` permissions; `<!--
archkeel-component-graph -->` compares them with observed imports (AD-57). Their edges may differ without drift.
`graph.drift` names the marker and both missing/extra edge sets relative to its own
source. Pages can carry either marker, both or neither; the contract's provenance
still requires exactly one observed marker. `init` writes no Target marker because
its draft decides no dependencies. See [graph writing](reference.md#results).

`forbidden_construct` fields are `source`, `constructs` and optional `allowed_sources` and
`exact_sources`, which exempt owners the way `external_dependency_scope` exempts modules. An
owner is the qualified scope a construct is written in, a module, class or function such as
`sample.cli.main`; an annotated variable's owner extends one segment further, to the variable
itself, at the module, class or function scope it is written in, such as
`sample.cli.main.parse.timeout` (AD-62). An
`allowed_sources` prefix exempts it and every scope nested in it, an
`exact_sources` entry only the scope it names (AD-49). The shop sample exempts exactly
`shop.cli.main.main` from its broad-except rule, and the demo rows `class-a-broad-except-exact`
and `class-a-broad-except-prefix` run one nested handler under each list: reported, then allowed.
`allowed_type_ignores` permits one suppression without exempting other constructs (AD-133):

```json
{"qualified_name": "probe.operations.execute_sql_script", "line": 4,
 "statement": "client.execute_sql_script(query)", "tag": "[attr-defined]"}
```

Each entry requires these four exact fields. `statement` is the attached AST statement rendered
by `ast.unparse`; `tag` is the trimmed comment suffix after `type: ignore`. A standalone comment
has no allowable statement. A sibling or compound header on the statement's first line also
prevents a match; an unambiguous multiline call remains supported.
Moving the line or changing the function, statement or tag leaves
the suppression forbidden; an identical second ignore also fails. Legacy type-ignore owner
selectors still use the module. A matched `type_ignore_allowance` fact cites the rule and its
decision provenance in JSON and HTML. Adding or changing an allowance widens under `--against`.
Unknown fields and duplicate entries are rejected.

Supported constructs are `getattr`,
`hasattr`, `cast`, `eval`, `exec`, `dynamic_import`, `type_ignore`, `any_annotation`,
`placeholder_body`, `assert`, `broad_except`, `setattr`, `delattr`, `vars`, `dunder_dict` and
`string_literal_compare`. `placeholder_body` covers a function body that is
only `pass`, `...` or a lone `raise NotImplementedError`, and exempts a method carrying
`@abstractmethod` or `@overload` and a method of a class that has a base, where emptiness is the
interface rather than a missing implementation (AD-29). `setattr`, `delattr` and `vars` are calls
written bare or as `builtins.<name>`, and `dunder_dict` is any `x.__dict__` access.
`string_literal_compare` is a comparison where `==` or `!=` has a `str` literal or an unambiguous
module/class name bound once to a `str` literal on one side, an `in` or `not in` test against a
non-empty tuple, list or set literal of `str` literals or such names only, or a `match` statement with a `str`
literal value pattern in any case, wherever it stands; it counts once per comparison and once per
`match` statement, and `if __name__ == "__main__":` is not counted. `Final` is only an annotation;
it does not add a second rule. Imported, dynamic, conditional, reassigned or otherwise ambiguous
names are not guessed, and Enum members remain outside this construct. Whether a compared value is
a closed vocabulary is still decided by `source` and `allowed_sources` (AD-48, AD-80). It matches
typing-signal records from direct AST calls, type-ignore comments and
`Any` in a parameter, return or variable annotation, and construct records from `assert` statements,
`except` handlers with no type or with `Exception` or `BaseException`, alone, in a tuple or as
`builtins.Exception` (`except Exception: raise` counts), empty bodies, and the reflection and
string-literal forms above. One record is one violation, so an
annotation repeated across a serialisation boundary reports once per position. Aliasing first, such as
`f = getattr; f(value, name)` or `E = Exception; except E:`, is not resolved and remains a blind
spot.

`complete_external_scope` fields are `source` and `rationale`. Every import below `source` whose
target is neither a scanned module nor part of the standard library must be covered by an
`external_dependency_scope` rule; an import no rule names is a violation naming the importing
module. It closes for dependencies what `complete_assignment` closes for modules, so a package the
contract never mentions — including one that does not exist anywhere — stops passing silently
(AD-28). The standard library is read from the analyzer's own Python version, which the
observation records, so a version change can move a module into or out of the exempt set.
Relative imports are internal by construction and are never counted. A dependency only the
package root imports is covered by a rule whose `exact_sources` names that root, so covering it
does not allow it in every module below (AD-49).

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
rule nothing changes, so a compatibility contract that never adopts it keeps deciding pairs one
by one. Each `requires.component` must name a component in that same contract, even without
this rule or any observed import. Unknown targets are invalid input with a pointer to the
entry; ancestors and other mounts do not supply missing labels. Component labels must be
unique within each contract, but may repeat across different levels or mounts (AD-113). A
`render` component that imports `model` without requiring it is an example violation. The same
rule kind is evaluated a second time against a component's declared inside, over the imports the
outer scan already collected, so a crossing between two sub-components that no `requires` entry
covers is a violation of the inside's own rule (AD-34). An inside's rules are recorded under the
component holding them, as `<component>:<rule id>`, and its violations name them there, so the
finding reads `store:STORE-REQUIRES-COMPLETE` rather than the bare id the inside contract wrote
(AD-36). The same prefix keeps the two levels apart: a `complete_requires` an inside declares
decides that level's pairs, never the pairs above it.

Contract 2.3 adds optional nonempty, case-sensitive component `layer` labels. They describe
architect intent and appear in Details; they do not change ownership or infer permissions.
Optional `layer_order` rules assess **declared `requires` permissions**, even without an import:

```json
{"id":"LAYERS", "kind":"layer_order", "layers":["Core","Adapters","Edge"],
 "rationale":"Inner layers cannot require outer layers.",
 "provenance":["docs/architecture.md"], "decided_by":"architect"}
```

`layers` runs inner to outer. Earlier→later FAILs; reverse and same-layer permissions are
allowed. Optional `components` selects source component labels at this contract level;
their required targets must also have a layer in the order. Missing or unlisted affected layers
are UNKNOWN. The assessment cites the real contract file and its loaded digest, never a
fabricated import. Actual imports remain governed by `complete_requires` and existing
dependency rules. Older contract versions reject both new fields; absent layers retain old
canonical bytes. Target graphs carrying layers and their report envelopes use 1.2;
legacy 1.0/1.1 graphs remain readable in report 1.0.

Inside contracts use the shared rule evaluators over the same scan (AD-110). Source modules
are limited to the parent's packages; global targets and origin signatures remain available.
Missing contracts and unsupported rules remain incomplete, never PASS. The report marks an
inside edge green only when every displayed import site has evaluation evidence and no
relevant UNKNOWN or edge violation remains. A green edge is not a component-wide certificate.

An `inside` can name another contract recursively (AD-111). Paths are relative to the selected
`--root`, not to the referring file. Each level owns its own component labels and rule ids:
`store:backend:NO-EVAL` names a rule inside `store`'s `backend`. Reusing a contract file under
two parents, cycles, escaping paths and colliding scoped ids are rejected. No directory gets a
contract implicitly. Inside contracts may declare exact `modules`; other nonempty
`declarations` fields are unsupported and refused. Component `public` entries and rule
provenance are separate supported fields.

`public` applies at its own contract level (AD-112). A child's API is available to local
siblings, not automatically to callers outside its parent. The parent explicitly publishes
its outward entries or proven facade reexports; the lists need not be equal or subsets.
A parent facade may sit outside all child packages. Namespace, provenance and `public`/`planned`
ownership and underscore checks also apply inside, with mount-qualified diagnostic pointers.
Ancestor restrictions still apply. `inside.public_mismatch` is no longer emitted.
With a local `interface_boundary`, an unscanned public module is `interface.missing`.
Nested unused-public and planned-promotion checks use scoped evidence (AD-115): cross-sibling
imports and explicit child or ancestor facades physically within the current parent. A
re-exported function counts at its publisher, not its definition's location. Unrelated facades
and unpublished parent imports do not count. A built, unused planned entry stays target work;
a reached one requires promotion without granting access. Unknown import names are not proof
of non-use. Root baseline exceptions do not transfer to children with matching labels.

`external_dependency_scope` fields are `dependency` (a top-level import name), `allowed_sources`
and `exact_sources`, at least one of the two non-empty. It matches import records whose target is
the dependency or one of its submodules, including `TYPE_CHECKING` imports, and allows those whose
source module falls under an `allowed_sources` prefix or equals an `exact_sources` entry. A
package root is a prefix of every module in its package, so only `exact_sources: ["sample"]`
allows `sample/__init__.py` a dependency that `sample.core` may not import (AD-49).

`complete_assignment` has the field `source`. Every scanned module below `source` must belong to
exactly one component; a module matched by two different components counts as unowned, while
one component may list nested packages. AST-empty files are exempt; a non-empty `source`
module needs an owner, including a docstring, version assignment or re-export initializer.
For compatibility, assignment exempts blank ordinary modules too. Boundary scope proof
(`complete_requires` and `interface_boundary`) exempts only unowned AST-empty Python
`__init__.py` files: ordinary module identities must still have exactly one owner. A module fact cites its file: line 1 when that line holds text,
otherwise the file itself as line 0, so a module whose first line is blank is still a traceable
violation (AD-107).

`root_layout` has `root` and an exact `allowed_children` list. Each allowed entry must be exactly
one name segment below `root`; the root itself, nested descendants, and entries under another root
are contract-invalid (exit 2). It checks each observed immediate package or module below `root`;
the root module itself is ignored, and an allowed child that is not yet present is not a violation.
An unexpected child is a normal baselineable violation, the same one whether its `__init__.py`
is empty or not: the file is the evidence (AD-107).
Adding an allowed child widens the contract; removing one narrows it. Adding the restriction
narrowing and removing it widening are enforced by `validate --against` (AD-86).

`component.namespace` is optional. It names one of that component's `packages` as its physical
home; `packages` remains the ownership set. Every observed module owned by the component but
outside that namespace is a baselineable `module.placement` violation. Contracts without the
field keep the old ownership-only behavior. A namespace is a package name, not a string path or
special case; adding it narrows `--against`, while removing or changing it widens the contract.

`no_component_cycles` has two optional fields, `level` and `components` (AD-98). Without them it
projects import records, including `TYPE_CHECKING` imports, onto components and reports each
strongly connected component with two or more members. Unowned-module imports are invisible;
combine it with `complete_assignment`.

`level: "module"` judges the module graph instead: each `module_scc` record the report measures is
one `module_cycle` violation. It names the SCC's members, its `edges` and, as facts and evidence,
every import between two members; each of those imports closes a cycle. A module cycle inside one
component is invisible to the component level, and a component cycle need not be a module cycle,
so a contract that cares about both declares two rules. `components` lists declared component
labels and reports only a cycle with a member under one of their packages (at the component
level, a member that is one of them); the cycle is still reported whole, unowned members
included. Matching by package prefix rather than by owner keeps a member that two overlapping
components both claim inside the scope. The default `level` is `component`, which the canonical contract
omits. A violation's fingerprint is its rule and members, so `--baseline` holds known SCCs and
fails on a new one. A cycle whose members are a strict subset of a baselined cycle is that cycle
contracting: `validate` reports a `contracted violation` to write back, `--write-baseline` needs
no `--accept-new` for it, and under `--against` the replacement narrows the baseline. Splitting
`{a, b, c}` into `{a, b}` contracts; `{a, b, c}` into `{a, b}` and `{c, d}` makes `{c, d}` new.
Under `--against`, changing `level` in either direction, adding a `components` scope and dropping
a listed component widen the contract; removing the scope and listing another component narrow
it.

The report's `package_scc` records roll modules up by their first two dotted segments, so two
packages can form a cycle that no import cycle closes. Each record's `backed_by` names the module
SCCs with members in two or more of its packages; an empty list marks the cycle `roll-up only` in
its title and in the `rollup_only_package_cycles` metric.

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
a declared name; underscore names never qualify. An entry is *reached* in one of two ways, and one
notion of `public` covers both (AD-65): a cross-component import that resolves to it, or a
declared facade signature of any component that names the type it declares, which exposes that
type to every consumer of the signature without an import of its own. The second reading uses the
`facade_types` the analyzer records on declared facade functions and classes with a proven
inherited generic method surface (AD-121), resolved by `boundary_types`' own resolution below,
so the rule that asks for such a type to be declared and
the check that asks whether declaring it was worth it read one answer, not two. An import a `forbidden_dependency` rule already
rejects is reported once, as that violation, and never also as `interface_boundary` (AD-18). An empty
`__all__` reads the same as no `__all__` at all, and aliasing during a re-export is not resolved;
these remain blind spots. `from pkg import name` follows Python's own precedence (AD-53): a
top-level `def`, `class`, assignment, aliased import, or `from` import in `pkg/__init__.py` that
binds `name` to anything but the identically named submodule wins over that submodule, so the
import is matched as the name `pkg:name`; a plain `from . import name`, which really does bind
the submodule, and no binding at all both match as the module `pkg.name`, exactly like `import
pkg.name`. Only an unconditional top-level statement in `__init__.py` counts. A `pkg/__init__.py`
that defines `__getattr__` or holds a star import the scan cannot expand makes every one of its
attributes undecidable; the scan keeps the module-if-it-exists reading there instead, which may
then disagree with what a particular attribute returns at runtime, and `validate` can report a
`pkg:name` public entry as `interface.unused` while the violation beside it names `pkg.submodule`
([#23](https://github.com/rapiddweller/archkeel/issues/23)). Importing `sample.core.impl`
directly from `sample.cli` when `core` declares only `sample.core` as public is an example
violation.

When a schema 1.1 baseline role disappears, `validate --baseline` may use that before-evidence
together with the fingerprint subjects to prove the exact cross-component importer that was
removed. If the target still lists that module or symbol as `public`, only its matching
`interface.unused` diagnostic is suppressed; `failures` reports the resolved violation and says
to remove the unreached entry (AD-85, #80). A 1.0 baseline, an unrelated role, an
intra-component role, or an ambiguous target cannot prove the narrowing, so the normal diagnostic
remains.

Private attribute access is a separate measurement. A private expression rooted in an untyped,
unresolved, or top-level `Any` parameter produces `private_attribute_access_limit` UNKNOWN: the
function, parameter and attribute are named, but runtime component ownership is not guessed. `Any`
nested inside `list[...]`, `dict[...]` or another outer typing form does not erase that outer
owner's deterministic type. Typed parameters, locals and public attributes are excluded. The UNKNOWN contributes to the separate
`untyped_private_accesses` scalar and the `unknowns` delta dimension, without becoming an
`interface_boundary` violation or changing confirmed `private_crossings` (AD-83).

A contract may name a target architecture ahead of the refactoring that builds it, so `validate`
tells a facade that is not built yet from one that never will be (AD-56). An unused `public` entry
is `interface.missing` when its module was never scanned — it names something that does not exist,
whether that is a typo or work still to do — and stays `interface.unused` when the module exists
but nothing reaches it, neither an import nor a declared facade signature (AD-65). A `pkg.module:Name` entry is judged by its module
alone: the `symbols` section records only classes and functions, so treating an unmatched name as
missing would misreport a module-level constant or type alias that the scan cannot see. A
component's optional `planned` list holds entries in the same `pkg.module`/`pkg.module:Name` shape
as `public`, disjoint from it: an entry the scan has not built yet is target work and gets no
diagnostic. A built entry remains target work until a cross-component import or a declared facade
signature reaches it; then `interface.planned_built` asks you to move it to `public` and drop it
from `planned` (AD-79). `planned` entries are held to the same ownership,
underscore and namespace checks as `public` ones, but never reach the analyzer: `planned` is not
projected into the observation, so it earns no `agent_decisions` count and grants no public access.

`sibling_isolation` has the field `members`, at least two dotted prefixes, and the optional
`include_type_checking` (default `true`). Peers reach shared modules and are reached from outside,
but never each other: the analyzer reports every import whose source and target lie in two
different members. One rule replaces the n*(n-1) `forbidden_dependency` rules the same intent would
otherwise need, and it stays inside a component, where no component pair decision applies. Archkeel applies it to the eight analyzer collectors (AD-1, AD-25).

`symbol_placement` fields are `source`, `class_kinds` and, matching `forbidden_construct`,
`allowed_sources` and `exact_sources`, at least one of the two non-empty. It states that a class
of a named kind below `source` is defined only in an allowed module: `class_kinds` names one or
more of `protocol`, `enum`, `pydantic_model`, `dataclass` and `class`, the same five values
`class_kind` resolves through the fixpoint over base classes `symbols.py` already runs, so the
rule is a selector over records the analyzer already carries. It matches every `class` symbol
record whose `class_kind` is named and whose qualified name falls under `source`, and allows one
whose own module falls under an `allowed_sources` prefix or equals an `exact_sources` entry
(AD-49); every other one is a violation. A class whose base is an unresolved alias inherits
`class_kind` through the same blind spot `class_kind` itself carries. Declaring a `Coupon`
dataclass in `shop.model.promotions` when `MODEL-TYPES-IN-ENTITIES` allows only
`shop.model.entities` for a dataclass below `shop.model` is an example violation (AD-58).
For shared types, choose the owning component before writing the rule; `foundation` is not a
default owner for domain enums or models. Set `source` to the package and use `exact_sources`
for the chosen module. The [target-first guide](target-first.md) has the complete contract
fragment. `init` does not infer this decision.

`boundary_types` has `source`, optional prefix `allowed_sources` and optional
`exact_sources`. It checks declared facade parameter/return types for broad
`dict`/`object` containers and unpublished owned types. Builtins, enums, Pydantic
models and types published by their actual owner qualify. A proven
`datetime.datetime` import is a scalar leaf; shadowed/unproven imports remain
UNKNOWN (AD-132).

Only a function `component.public` itself covers is inspected -- a module-level entry makes every
non-underscore name of that module a facade function, or its `__all__` when it declares one, and a
`pkg.module:Name` entry makes exactly that one, the same reading `interface_boundary` gives
`public` (AD-9) -- exempts one whose own module falls under an `allowed_sources` prefix or equals
an `exact_sources` entry (AD-49), and reports distinct violations within parameter and return positions whose
annotation is exactly `dict`, `Dict`, `object`, a `dict[...]`/`Dict[...]` generic, or a bare name
that resolves, through the same import bindings `interface_boundary` reads, to a class that is
neither an `enum` nor a `pydantic_model` by kind and that no component's own `public` list
declares. Builtin spellings are proven only without a module-scope shadowing binding. A shadowed
parameterized spelling whose generic target is unresolved stays UNKNOWN and cannot consume an
exact allowance; a bare name resolved to a known local non-public type may still violate. A
function re-exported by a declared facade entry is checked at its definition, while
the violation keeps the facade module and entry as its subject. For an ordinary module (not
`__init__.py`), following an imported entry requires one unchanged literal `__all__` that exports
its unique import binding, whose terminal definition also has one unambiguous binding; an import
alone does not prove it is a facade (AD-109). Multiple proven aliases to one exact origin do not
duplicate a finding. Missing, ambiguous or unstable public alias routes remain UNKNOWN, even if
another function in the facade can be checked. Exported classes expose effective public methods,
constructors and special methods along one proven local base chain, with verified generic
substitutions (AD-145). Signatures resolve in their defining module; subclass bindings override
base members. Private helpers stay excluded. Unproven bases, multiple-base precedence, mutations,
class transformations and unproven method decorators preserve `inherited_surface` UNKNOWN.
Direct signatures are checked as declared. Property and repeated-name chains use
proven effective bindings. When a chain cannot be proven, its source-declared positions remain
UNKNOWN candidates with raw annotations and source evidence (AD-153). Candidates do not prove
runtime signatures, expose types or consume allowances. Their counts can rise without a code
defect being fixed; existing UNKNOWN budgets still apply.
A named type may be public through its owner's proven facade export; it need not expose its
implementation module. Without a proven public route, a matching uncertain export is UNKNOWN.
An export by another owner does not grant publication. Public model fields are still checked.
An inherited generic signature that is a possible but unproven use produces
`interface.usage_unknown`, not `interface.unused`, at root and inside scopes, including uncertain
re-exports (AD-149); it is not added to `facade_types`. A proven
import or facade signature still wins over that candidate.
Owned model fields, supported collections and unions are inspected recursively (AD-93). A repeated
type ends only its current traversal path. Findings retain the signature-rooted field path;
distinct bad union members are separate findings, not duplicate reports of one position.
Supported collections include `list`, `tuple`, `set`, `frozenset`, `Sequence`, `Iterable`,
`Iterator`, `Collection`, `AbstractSet` and their `typing` spellings. A collection is only as
decided as its members; `dict[...]` remains a broad container under this rule.
`Required[T]` and `NotRequired[T]` expose `T` when their import from `typing` or
`typing_extensions` is proven; lookalikes and malformed arguments remain UNKNOWN (AD-122).
Unsupported annotation shapes, unresolved names, missing annotations and externally owned types remain
undecidable. Each rule files one UNKNOWN `boundary_type_limit` record
in `unknowns`, carrying the positions it saw, the positions it decided and a count of each
undecidable kind, with explicit coverage (AD-67, issue #59). It changes no diagnostic,
`coverage.rules` or exit status. It does move `declared_rules`: a violation-free
observation reads UNKNOWN there, not PASS, if an undecided position's reason is a real checker limit,
but stays PASS when every undecided position is `external_type` (a type owned by no declared
component), since a rule with no `public` list to check that type against never had the question to
answer (`inspect_observation`, AD-67). A component that declares no `public` at
all has no functions for the rule to inspect, the way `interface_boundary` gives it no imports to
check either; a `planned` entry (AD-56, AD-79) is never projected into the observation, so it plays no
part here, the same as everywhere else in the analyzer. A module named by an exact `planned` entry
is declared target work even before it is scanned; it avoids `rule_without_subjects` without
becoming an observed public interface (AD-79). A scope with no matching planned entry remains no subject. A
`source` that matches a scanned module but whose declared facade covers no function of it reports
`rule_without_subjects`, UNKNOWN, not PASS (AD-63, issue #56).

Publishing a type in its owner's `public` list can resolve a finding: the same
facade signature proves its use (AD-65). For runnable positive and negative cases,
see [the demo catalog](architecture-demo.md).

Proven standard-library `Mapping[K, V]` and `MutableMapping[K, V]`, and a bare `Mapping` or
`MutableMapping`, are also broad map findings: changing `dict` to an abstract mapping does not
declare a record shape (AD-123). Their member types are still checked. Unproven or malformed
subscripted mapping annotations remain UNKNOWN, not a clean pass; a bare name the analyzer
cannot prove to be a standard-library mapping (`from mylib import Mapping`) is judged like any
other external type.
An undecidable mapping member retains UNKNOWN alongside the known broad-map violation.
Mixed union or DTO findings likewise retain both known violations and UNKNOWNs.

`allowed_positions` may exempt one finding by exact `qualified_name`, `position`,
`field_path` and `annotation`. An omitted or empty `field_path` selects the parameter or return itself;
its `annotation` must match the complete signature annotation. A nonempty `field_path`
names a nested field relative to that position and matches its complete declared annotation,
including nullable unions. Matching uses the collector's annotation text; `Optional[T]` and
`T | None` are distinct selectors. A member permission cannot exempt a nullable field.
Multiple maps or ambiguous declarations at the same path remain unallowed. A compound-field
permission selects one outer map; other bad members, nested map values and UNKNOWN remain visible.
Neither selector hides an unresolved union or mapping member.
A direct-map allowance applies only when the signature has one top-level broad-type
finding; it never covers a nested map or an undeclared member. Multiple
top-level broad findings leave that allowance unused. A root `annotation` cannot be a bare
`Dict`, `Mapping` or `MutableMapping`; the contract is rejected (AD-95). Other spellings of a
bare mapping (`typing.Mapping`, an alias) never match.
An exact root `object` or `object | None` allowance accepts an opaque native payload (AD-135).
The complete annotation must match; a literal `object` decision never accepts a nullable return.
It emits `accepted_opacity: true` with the owning decision's provenance; type closure remains
unproven. Other parameters, returns, constructors, masks and UNKNOWNs remain checked.
A previously inert empty-path allowance for a complete collection or union annotation can now
apply when its signature contains exactly one pathless parameterized mapping occurrence, at any
depth. The mapping annotation and depth are recorded in its `FACT`. Identical siblings count
separately. The contained fallback is unused when multiple pathless maps occur. Existing direct
and DTO allowances keep their behavior: an allowed direct map may coexist with a contained map,
whose finding remains. A named type alias on the route to the selected mapping also leaves it
unmatched.
A mismatch leaves the violation intact, and a
bare `dict` cannot match an allowance for `dict[str, JsonValue]`. Applied entries produce a
`FACT` in `typing_signals` linked to the rule and function evidence; an unused entry emits no
fact and has no effect. Adding an entry widens the contract and needs an amendment under
`validate --against`; removing one narrows it (AD-95).
An allowance removes only its matching violation; member findings and UNKNOWNs remain visible.

An explicit positive-integer `container_depth` selects a literal `object` map value (AD-142):
`{"qualified_name": "sample.api.validate_raw", "position": "values", "annotation": "dict[str, object]", "container_depth": 1}`.
For `dict[str, list[object]]`, depth 2 selects the value's literal builtin-list element (AD-189).
Both `list` and `object` need proven builtin bindings; rebinding or ambiguous imports cannot grant permission.
The outer map needs its own entry without that coordinate. The complete signature annotation,
symbol and parameter/return must match; the field path must be empty. Each enclosing collection
or mapping adds one depth; unions do not. Only one alias-free, pathless mapping and one matching
opaque occurrence before finding deduplication can apply. Keys, duplicate siblings, alias-wrapped
values, deeper value collections, nullable list elements, bare dictionaries, `Any`, other positions and UNKNOWNs stay checked. The FACT records
depth, `nested_annotation: object`, `accepted_opacity: true` and decision provenance. Accepted
opacity does not prove type closure. Omitting depth preserves existing wire bytes and digests.

### Known violations of a target contract

A contract may state the architecture the code is heading for rather than the one it has, in
which case every class A rule above is violated by design until the refactoring lands. Freeze
those violations instead of weakening the rules (AD-52):

```bash
archkeel validate --baseline known-violations.json --write-baseline   # initial file, then review it
archkeel validate --baseline known-violations.json                    # the gate
archkeel validate --baseline known-violations.json --write-baseline   # resolved-only cleanup
archkeel validate --baseline known-violations.json --write-baseline --accept-new  # deliberate widening
```

Paths resolve inside `--root`; invalid/unreadable baselines produce
`baseline.invalid`, exit 2. Fingerprints use rule IDs and subjects, without line
positions. Counts must match exactly; new/resolved drift exits 1. An exact baseline
can exit 0 with `declared_rules: FAIL`. Other diagnostics remain exit 2.

Existing baselines are compared before writes. Resolved-only drift can be written;
new/increased fingerprints require `--accept-new` after a decision. `baseline_new`
and `baseline_resolved` count changed fingerprints, not occurrences.

Schema 1.3.0 holds violations, selected measurements, accepted facade/coupling names
and optional directional `roles`. Roles are protected evidence without changing
fingerprint identity. Schemas 1.0/1.1/1.2 remain readable. See
[the reference](reference.md#results) and
[baseline schema](https://github.com/rapiddweller/archkeel/blob/main/schema/violation-baseline.schema.json)
for fields and resolved-import narrowing.

### Project gate

Archkeel does not own a generic project-command configuration. Each repository owns one explicit
Make entry point that names its locked checks and then its Archkeel validation:

```make
.PHONY: gate
gate: check self-validate

self-validate:
	uv run --locked archkeel validate --root . --baseline architecture-baseline.json --json
```

Keep commands as Make prerequisites, without pipes or output-tail filters. Make's nonzero status
must reach CI; a later step must not mask a failed project check.

### Contract widening

The easiest way to "fix" a violation in the target-first workflow above is to widen the target
in the same change: add a `requires` edge, a `public` entry or an `allowed_sources` module,
relax or delete a rule, or pad the baseline. `--against <ref>` classifies every difference from
the contract at that Git revision (and, with `--baseline`, the baseline file there too) as a
widening or a narrowing (AD-61, #11):

```bash
archkeel validate --against origin/main
```

Widening is a new permission or a dropped restriction; narrowing is each reverse, and always
passes. `boundary_types` and `symbol_placement` are restrictions too. A difference this
classification does not name is reported as a widening, never passed over silently. A package
renamed together with every module name the contract gives it widens nothing: it is recognised,
named under `renames` and compared away, so only a widening beside it fails (AD-105). The CLI
reads the same selected `--config` from the pinned historical revision; missing or invalid config
cannot authorize a rename. Every Python rename candidate needs a complete historical layout scan,
even when roots and namespace are unchanged, because physical layout may move within those roots.
Changed-root Dart remains unsupported; same-root Dart renames keep their existing behavior. A
widening fails (`failures`, exit 1) unless `--amendment <path>` names a file
binding its recursive contract and canonical baseline policies on both sides, recording who decided it and why:

```bash
archkeel validate --against origin/main --amendment widening.json \
  --write-amendment --decided-by "Jordan (architect)" --rationale "..."   # once, reviewed
archkeel validate --against origin/main --amendment widening.json         # the gate
```

An amendment written for one change does not verify against a different one: its digests will
not match. A contract the revision does not hold yet, a new scope's or a moved one's, is one
widening, `contract introduced: <path> does not exist at <ref>`, amended the same way (AD-104).
The comparison includes every mounted inside contract, canonically, so whitespace alone is not
a policy change. **Migration:** an older root-only amendment for a tree with inside contracts
must be regenerated and reviewed with the command above. It is not silently accepted against
the larger policy tree. No-inside amendment digests and existing one-level finding ids retain
their meaning. Observation digests still bind the actual contract bytes (AD-111).
A missing or malformed `--amendment` file, or one outside the root, is
`amendment.invalid`, and an `--against` revision,
or a contract or baseline there that cannot be read, is `against.invalid`, both exit 2.
`validate` without `--against` is unchanged. The file's shape is
[`schema/contract-amendment.schema.json`](https://github.com/rapiddweller/archkeel/blob/main/schema/contract-amendment.schema.json).

## Class B: regression checks

Regression checks compare accepted and candidate observations. They include scalar counts,
integer cross-multiplied ratios and semantic fingerprints.

- **Measurement:** `calls_unresolved`, `unresolved_ratio`, typing positions, cycles, private
  crossings, `untyped_private_accesses`, `unknown_positions`, violations and coverage failures.
- **Compatibility:** both observations need comparable Python and analyzer versions.
- **Blind spots:** a stable count can hide replacement of one finding by another; fingerprints
  cover supported semantic changes, not intent.
- **Example:** reject a candidate whose unresolved call count rises from 0 to 1.
- **Evidence:** `unresolved_call_changes` names each added or removed unresolved call by caller,
  expression, path and lines, keyed without the line so moved code is no change, and
  `report --only calls --json` lists every unresolved and partially resolved call (AD-100).

`coverage_failures` is measured but cannot regress between two comparable observations: an
incomplete scan produces no measurements, so the check reports NOT CHECKED instead.

`declarations.measurement_budgets` selects already-produced scalars for `validate --baseline`:
`cycle_edges`, `private_crossings`, `typing_positions`, `calls_unresolved`,
`untyped_private_accesses` and `unknown_positions`. Baseline schema 1.2 and later stores their
exact accepted values. A rise fails; a fall also fails until `--write-baseline` records it.
Missing measurement evidence exits 2, never PASS (AD-89). The baseline stores values only; without
`--against` a `calls_unresolved` rise says so, and on a failing run `--against <ref>` names the call
sites behind the change, or says why it names none (AD-100).

`declarations.facade_budgets` and `declarations.coupling_budgets` state targets.
`{component, max_names}` targets the `module:name` entries a component's `public` modules export;
`{source, target, max_names}` the target facade names the source imports, following re-export
chains the way `interface_boundary` does and counting `TYPE_CHECKING` imports. A name reachable
through two declared modules counts once per module. Without `--baseline`, a count over
`max_names` is `budget.exceeded`, listing every counted name because a count cannot say which are
too many. With `--baseline`, the file holds each budget's accepted names instead: a name outside
them is a rise in `failures` that needs `--accept-new`, a name gone is a fall until
`--write-baseline` records it, and accepted names over the target are a known gap reported as
`over_target`. A count the scan cannot complete is `budget.unknown` at exit 2 in both modes: a
whole-module entry whose `__all__` is not one non-empty literal assignment nothing else changes,
a whole-module import of a facade module, a star import of a non-enumerated facade, or a name a
non-enumerated facade does not list. A key naming no component, a budgeted facade
without `public`, a pair naming one component twice, a repeated key, and a pair budget without an
`interface_boundary` rule that includes `TYPE_CHECKING` imports are `contract.invalid`. Raising or
removing `max_names`, growing an accepted name set in the baseline, or accepting more names than
the old `max_names` for a key the old baseline did not hold widens under `--against`
(AD-99).

## Class C: declarations

Fields under `declarations` preserve capabilities, review scopes, external API,
commands, context roots, paths, owners and budgets. Names must resolve within the
configured namespace (`reference.namespace`); provenance files must exist
(`reference.provenance`). All fields are decoded; facade/coupling budgets are read
only by `validate`.

Component `public` governs internal crossings. `public_api` promises names to
external consumers, so it has no unused-entry check. Its scanned modules, literal
exports and resolvable exposed types are validated. Ambiguous bindings/types stay
UNKNOWN. See [external API checks](reference.md#reading-a-reports-violations).

Responsibilities, paths and ownership judgments are recorded verbatim; their truth
is not proved. A judgment that reduces to an observed fact belongs in class A.
A broader evidence-bound review claim belongs in class D and remains HYPOTHESIS.

## Class D: review claims

Class D names what one observation suggests and a person decides. A claim is a triple: a signal the
analyzer records, a pure derivation in `ir`, and a report section without a verdict (AD-26). A claim
whose signal is missing reports UNKNOWN and lists nothing, so an analyzer that cannot produce the
signal costs the other claims nothing.

Claim derivations are deterministic for one observation, but never produce rule
verdicts or exit status. Every command that derives a claim also names it: `report` and `validate` print the counts in the
terminal and carry them under `claims` in `--json`, where a missing signal is `null` rather than
zero, while the HTML report lists the candidates themselves (AD-35). None of this reaches an exit
code.

`unreferenced symbol` is the first claim. Its signal is the `references` section, which records
every use of a scanned symbol that is not a call: a function put into a table, passed as an
argument, or read as a property. The derivation names each symbol that no call, reference or import
inside the scan scope mentions, after setting aside dunder names, `__all__` entries and methods of a
subclass, which the runtime dispatches without naming them. For this claim, an `Enum.MEMBER`
expression references its enum class only when the class binding and recorded literal member both
resolve statically (AD-108), and the root has one direct module-level class/import binding with no
competing binder anywhere in that module. Type-parameter declarations also suppress enum-member
evidence for the whole module. These conservative bounds can suppress valid evidence when an
unrelated scope binds the same name; they avoid introducing a second Python scope resolver.
The defining enum binding must also be unambiguous. Scanned attribute writes/deletes invalidate
overlapping qualified targets; an ambiguous imported writer suppresses this augmentation.
Alias-copy assignments and dynamic mutation are not followed: this is syntactic evidence,
not proof of runtime immutability. Other references, including explicit imports, retain their
existing meaning.

- **Measurement:** candidates, symbols examined, symbols set aside, and the unresolved-call share
  beside them.
- **Blind spots:** a consumer outside the scan scope, such as a test, is invisible; so is a name
  reached through a string, a registry or a plugin entry point. The resolver limits in
  `known-limits.md` reach the claim as false candidates: a method invoked on a call result, as in
  `Repository(root).save(...)`, names nothing the claim can see. That is why the unresolved-call
  share is printed beside the candidates — it is the size of that blind spot.

`unread binding` is the second claim. Its signal is the `bindings` section, which records every
parameter or local whose name no expression in its own function reads. This is a lexical fact, not
a test of whether removing the binding is safe: an implementation parameter may still be required
by an interface. Nothing is resolved across modules, so the claim is supported wherever the
analyzer ran. It sets aside a name with a leading underscore, which is Python's own mark for a
deliberately unused binding, `self` and `cls`. It also skips parameters in methods of classes with
any base, in decorated functions, and in empty function bodies. Those are syntactic heuristics; they
do not prove that a method overrides another or satisfies a structural interface.

- **Measurement:** lexical candidates, and the functions examined beside them. The bindings set
  aside are not counted, because the signal records only what it names. An empty list means no
  candidates were recorded; it does not establish that every parameter is read.
- **Blind spots:** a name bound by an import inside the function, by `except ... as` or by a
  `match` pattern is not recorded, and a read through `locals()` is invisible.

`repeated logic` is the third claim, and the only one that reads a class-C declaration. Its signal
is the `shape` each function and method symbol carries: the node types of the body in walk order,
hashed, with names, literal values and the docstring left out, so a renamed or re-documented copy
still matches its original. The derivation groups functions by shape and, for every declared
`spot_owner`, names each function outside the owner whose shape matches one inside it.

- **Measurement:** candidates, the declared owners examined, and the functions compared.
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
- **Blind spots:** the claim measures what a component holds, not how tangled it is — a component
  of many independent modules is named alongside one that is genuinely knotted. Physical
  navigation exposes the observed modules, but does not invent rules for undeclared boundaries.
  Explicit nested contracts are recorded, judged and drawn from the same observation (AD-34).
  Missing either signal reports UNKNOWN, because a
  comparison against zero component edges would name every component.
Review physical subtrees before adding `inside`. Do not rerun root `init --source`:
it targets standard onboarding files. Follow the
[boundary review guidance](onboarding.md#choose-the-boundaries).

`cross-component type fan-in` is the fifth claim (issue #9, AD-59). Its signals are the `symbols`
and `imports` sections: `imports` for which function or method a cross-component call reaches,
`symbols` for that function's own parameter and return annotations. The derivation groups every
crossing function once per ordered component pair it is called across, however many import sites
name it, collects the raw annotation string at every parameter and return position, and names
every annotation string that is passed across two or more distinct component pairs, most-crossed
first.

- **Measurement:** the annotated positions examined, and the candidates beside them.
- **Blind spots:** the annotation is the raw string a function declares, not a resolved type, so
  `Order` from one module and an unrelated `Order` from another are the same candidate; a call
  reached only through a re-export whose chain the scan cannot expand is invisible the way
  `interface_boundary`'s own blind spot is. A type that crosses many boundaries is not itself a
  problem, only the material a broad-context smell would show up in.
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
| `measurement_budgets` | `declarations.measurement_budgets` |

Set `schema_version` to `2.1.0`. The optional `$schema` points to
`schema/architecture-contract.schema.json`. Omit unused declaration arrays instead of copying
empty arrays. Put each permitted outbound component edge in its source component's `requires`
list and add one `complete_requires` rule; absence then forbids every other pair (AD-32). Run
`archkeel validate --root . --json` to verify the migrated contract.

V2 amendments require `before_baseline_digest` and `after_baseline_digest`; null means no baseline comparison. Missing files have a path-bound identity distinct from empty baselines. Digests use the original before policy, before rename classification, and the actual after policy (including an allowed baseline rewrite). Refused rewrites emit no amendment. Legacy v1 records authorize contract-only comparisons. An explicitly supplied stale record fails even without widening. Free-text authors and reasons do not authenticate approval.
