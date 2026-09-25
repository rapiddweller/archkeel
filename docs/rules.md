# Architecture rules

Contract 2.0 separates deterministic rules, regression checks, declarations and review claims.

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

Each analyzer profile declares, in `src/archkeel/ir/profiles.py`, which rule kinds it decides,
which it decides partly and which it cannot decide, and which scalars it does not measure. The
Python profile decides and measures everything. The Dart profile (`language = "dart"`) decides the
import-graph rules, `no_component_cycles` with `level: "module"` and `components` included, because
a library is a module and every directive edge is a FACT (AD-98); `interface_boundary` and a
`target_symbol` rule report UNKNOWN for an import without `show`; `symbol_placement`,
`boundary_types`, `forbidden_construct`, `context_roots` and a budget on an unmeasured scalar exit 2
with `rule_unsupported_by_profile` (AD-97).

## Class A: deterministic rules

`complete_requires` is the compact closed-world invariant Archkeel uses itself (AD-32): each
component lists its permitted outbound component edges under `requires`, and one
`complete_requires` rule makes every absent pair forbidden. An observed crossing no entry covers
is a violation. Contracts without that rule retain AD-15's pair-by-pair form: an undecided pair is
`decision.open`, duplicate pair rules are `closed_world.duplicate`, and an observed pair also
forbidden is `closed_world.observed_forbidden`. A complete scan and exact package assignment make
either form deterministic; dynamic imports remain a blind spot.

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

A contract page's marked graph draws what the code does; a second, optional marker,
`<!-- archkeel-target-graph -->`, draws what the contract permits, beside the always-required `<!--
archkeel-component-graph -->` (AD-57). A pair permits an edge by an `allowed_dependency` rule or by
a `requires` entry (below); the two together, never redefining either marker, since that would
silently change what a page already asserts. The target graph may differ from the component graph
- a permission not yet used, or debt the code has not yet shed - without either being wrong; only a
marker whose own edges disagree with its own source is `graph.drift`, and the diagnostic's subject
names which marker. The component claim calls drawn-but-unobserved edges **edges gone from code** and
observed-but-undrawn edges **edges new in code**. The target claim uses **edges gone from contract**
and **edges new in contract**, because it compares permissions, not imports. Both directions are
stated explicitly. A page may carry either marker, both or neither; `init` never writes the target
marker, since it drafts no dependency decision for `--write-graph` to draw (AD-15).

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
rule nothing changes, so a compatibility contract that never adopts it keeps deciding pairs one
by one. A `requires` entry naming a component that does not exist covers nothing and remains a
blind spot. A
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
makes the result deterministic. A module fact cites its file: line 1 when that line holds text,
otherwise the file itself as line 0, so a module whose first line is blank is still a traceable
violation (AD-107). Adding `archkeel/extra.py` without a component package is an example
violation.

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
strongly connected component with two or more members. A complete scan and exact package
assignment make the result deterministic. Imports between unowned modules are invisible; combine
it with `complete_assignment`. Importing `sample.cli` from `sample.core` while `sample.cli` imports
`sample.core` is an example violation.

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
it. Two `sample.core` modules importing each other is an example module-level violation that the
component level passes.

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
`facade_types` the analyzer records on each declared facade function, resolved by
`boundary_types`' own resolution below, so the rule that asks for such a type to be declared and
the check that asks whether declaring it was worth it read one answer, not two. An import a `forbidden_dependency` rule already
rejects is reported once, as that violation, and never also as `interface_boundary` (AD-18). A
complete scan, fixed source bytes and analyzer digest make the result deterministic. An empty
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
projected into the observation, so it earns no `agent_decisions` count and takes no part in an
AD-20 inside's public-surface match.

`sibling_isolation` has the field `members`, at least two dotted prefixes, and the optional
`include_type_checking` (default `true`). Peers reach shared modules and are reached from outside,
but never each other: the analyzer reports every import whose source and target lie in two
different members. One rule replaces the n*(n-1) `forbidden_dependency` rules the same intent would
otherwise need, and it stays inside a component, where no component pair decision applies. A
complete scan and fixed source bytes make the result deterministic; dynamic imports remain a blind
spot. Archkeel applies it to the eight analyzer collectors (AD-1, AD-25). Importing
`sample.core.first` from `sample.core.second` when both are members is an example violation.

`symbol_placement` fields are `source`, `class_kinds` and, matching `forbidden_construct`,
`allowed_sources` and `exact_sources`, at least one of the two non-empty. It states that a class
of a named kind below `source` is defined only in an allowed module: `class_kinds` names one or
more of `protocol`, `enum`, `pydantic_model`, `dataclass` and `class`, the same five values
`class_kind` resolves through the fixpoint over base classes `symbols.py` already runs, so the
rule is a selector over records the analyzer already carries. It matches every `class` symbol
record whose `class_kind` is named and whose qualified name falls under `source`, and allows one
whose own module falls under an `allowed_sources` prefix or equals an `exact_sources` entry
(AD-49); every other one is a violation. A complete scan and the same fixpoint that resolves
`class_kind` make the result deterministic; a class whose base is an unresolved alias inherits
`class_kind` through the same blind spot `class_kind` itself carries. Declaring a `Coupon`
dataclass in `shop.model.promotions` when `MODEL-TYPES-IN-ENTITIES` allows only
`shop.model.entities` for a dataclass below `shop.model` is an example violation (AD-58).
For shared types, choose the owning component before writing the rule; `foundation` is not a
default owner for domain enums or models. Set `source` to the package and use `exact_sources`
for the chosen module. The [target-first guide](target-first.md) has the complete contract
fragment. `init` does not infer this decision.

`boundary_types` fields are `source` and, matching `forbidden_construct`, optional
`allowed_sources` and `exact_sources`. It states that a component's declared facade function
below `source` takes and returns no bare `dict`/`object`, and no named type outside a builtin, an
enum, a Pydantic model, or a type some component -- whichever one actually owns it -- already
declares public: a target architecture where a component's own types are the only thing that
crosses its boundary rules out a broad container, and an undeclared type, standing in for one.
Only a function `component.public` itself covers is inspected -- a module-level entry makes every
non-underscore name of that module a facade function, or its `__all__` when it declares one, and a
`pkg.module:Name` entry makes exactly that one, the same reading `interface_boundary` gives
`public` (AD-9) -- exempts one whose own module falls under an `allowed_sources` prefix or equals
an `exact_sources` entry (AD-49), and reports one violation per parameter or return position whose
annotation is exactly `dict`, `Dict`, `object`, a `dict[...]`/`Dict[...]` generic, or a bare name
that resolves, through the same import bindings `interface_boundary` reads, to a class that is
neither an `enum` nor a `pydantic_model` by kind and that no component's own `public` list
declares. A function re-exported by a declared facade entry is checked at its definition, while
the violation keeps the facade module and entry as its subject. Multiple aliases or re-export
paths that resolve to the same exact origin are decidable as one origin; only distinct origins
make the facade position UNKNOWN (`ambiguous_facade`). If a declared request or result
type resolves to a scanned class, its directly declared fields are inspected one level deep with
the same broad-type test. An ambiguous or unresolved field, or a field that would require a
second model descent, is UNKNOWN rather than an inferred pass (AD-84). A known collection holding
a bare name -- `list`, `tuple`, `set`, `frozenset`,
`Sequence`, `Iterable`, `Iterator`, `Collection`, `AbstractSet` and their `typing` spellings -- is
decided from its type parameters by that same resolution, one level in, so wrapping a parameter in
a list no longer drops the check; a collection is only as decided as its parameters, and `dict` is
absent because a `dict[...]` is already the broad container above (AD-67). A builtin, and a name
resolving to an enum, a Pydantic model or a declared type, is a decided pass. A dotted name, a
mapping, a nested subscript, a union, a forward-reference
string, a missing annotation and a type owned by no declared component stay undecidable, because
deciding any of them still needs resolving where the name comes from in a way AD-37 and AD-40 leave
unfinished for a call's receiver and this rule leaves unfinished for them too (issue #9, AD-58,
AD-63). Undecidable is no longer silent: each rule files one UNKNOWN `boundary_type_limit` record
in `unknowns`, carrying the positions it saw, the positions it decided and a count of each
undecidable kind, so a reader sees how much of the facade the rule actually decided instead of
reading no violation as proof of none (AD-67, issue #59). That record reports and does not gate --
`coverage.rules`, the diagnostics and the exit code do not move -- because a rule that decided
nothing at all is already `rule_without_subjects`, below, and a rule that decided some of its
positions holds the verdict those positions earned. It does move `declared_rules`: a violation-free
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
`rule_without_subjects`, UNKNOWN, not a clean pass: a rule that can only pass by finding nothing to check is the same defect a declared
rule that cannot fail is everywhere else in this tool (AD-63, issue #56). Measured on Archkeel's own facades, the
restricted-string match alone still fires 26 times inside `archkeel.ir`, all of it the codec's own
untyped-JSON boundary and narrowing helpers such as `text_value(value: object) -> str`; a `source`
scoped to a component whose facade really is typed throughout, such as `archkeel.analyzer`, is how
Archkeel's own contract adopts the rule against itself (AD-63) without a growing
`allowed_sources` list carrying architecture knowledge it does not own. The answer a violation
asks for — declare the type in the owning component's `public` list — is a legal answer: the
declaration is reached by the very signature that exposed it, so `interface_boundary` no longer
calls it unused (AD-65). Fixed source bytes and
analyzer digest make the result deterministic. Adding a `snapshot(context: dict) -> str` function
declared in `shop.app`'s own `public` list, which `APP-TYPES-NOT-DICT` scopes to `shop.app`, is an
example violation, and so is `summarize_all(extras: list[Extra]) -> Money`, where wrapping the
undeclared `Extra` in a list is no longer a way out of the same finding (AD-67).

`allowed_positions` may exempt one nested DTO finding by exact `qualified_name`, `position`,
`field_path` and `annotation`. `field_path` is relative to the parameter or `return`; the
outer signature annotation stays in the violation record. The allowance applies only when
`data.path` and `nested_annotation` both match. A mismatch leaves the violation intact, and a
bare `dict` cannot match an allowance for `dict[str, JsonValue]`. Applied entries produce a
`FACT` in `typing_signals` linked to the rule and function evidence; an unused entry emits no
fact and has no effect. Adding an entry widens the contract and needs an amendment under
`validate --against`; removing one narrows it (AD-95).

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

The baseline path, like `--amendment`'s below, is relative to `--root`, as the contract is, or
absolute; one that resolves outside the root is `baseline.invalid`, exit 2 (AD-103).

Each entry names one violation by fingerprint — the rule ids it cites and its sorted `subjects`,
which per rule kind are the modules, the construct owner or the members of a cycle — plus the
number of violations sharing it, since two `getattr` calls in one function are one fingerprint.
A fingerprint holds no line or column, so an unrelated edit above a violating line leaves it
alone. Both lists are read in any order, so an entry whose subjects a text replace reordered still
names its violation (AD-106). Baseline schema `1.3.0` also carries contract-selected measurement
budgets, the accepted names of each facade and coupling budget, and may carry sorted `roles` objects
(`source` and `target`) for directional violation rows; they explain every crossing and never change
fingerprint identity. They are semantic evidence: `validate --against` rejects any role-only change
unless an amendment accepts it. Multiple roles are retained. Rows without a resolved direction,
including construct rows, omit `roles`. Schemas `1.0.0`, `1.1.0` and `1.2.0` remain readable. Counts
must match the observation exactly: a higher one is a `new violation`, a lower one a `resolved
violation`, both reported in `failures` with exit 1, so the budget only shrinks. An existing
baseline is compared before a write: resolved-only drift may be written, while new or increased
fingerprints refuse the write unless `--accept-new` is explicit. The refused run's last failure says
so and names `--accept-new`, for after an architect's decision. A run whose baseline is exactly
right exits 0, with `declared_rules: FAIL` still naming the debt. Only `rule.violated` is answered
this way: `decision.open`, `graph.drift` and every other diagnostic still exit 2. A baseline that
cannot be read is `baseline.invalid`, exit 2; an existing one is corrected by hand, since a write
reads it first. In JSON, `baseline_new` and `baseline_resolved` count fingerprints whose occurrence
count rose or fell. Each changed fingerprint contributes one, not its occurrence-count delta. The
file's shape is
[`schema/violation-baseline.schema.json`](https://github.com/rapiddweller/archkeel/blob/main/schema/violation-baseline.schema.json).

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
named under `renames` and compared away, so only a widening beside it fails (AD-105). A widening
fails (`failures`, exit 1) unless `--amendment <path>` names a file
binding its exact before/after contract digest, recording who decided it and why:

```bash
archkeel validate --against origin/main --amendment widening.json \
  --write-amendment --decided-by "Jordan (architect)" --rationale "..."   # once, reviewed
archkeel validate --against origin/main --amendment widening.json         # the gate
```

An amendment written for one change does not verify against a different one: its digests will
not match. A contract the revision does not hold yet, a new scope's or a moved one's, is one
widening, `contract introduced: <path> does not exist at <ref>`, amended the same way (AD-104).
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
- **Determinism:** both observations must use comparable Python and analyzer versions.
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

Fields under `declarations` preserve capabilities, review scopes, a package's external public
API, commands, context roots, paths, owners, measurement budgets and facade and coupling
budgets. Archkeel decodes every one of them and reports all but the facade and coupling budgets,
which only `validate` reads. It checks every one for two structural facts: a declared name
resolves inside the configured namespace (`reference.namespace`) and a declared provenance file
exists (`reference.provenance`).
`public_api` names the surface a consumer *outside* this package may rely on - a different thing
from the component `public` field, which names one component's promise to another component of
the *same* package and is held to `interface_boundary` at every crossing (AD-9). Nothing inside
the scan crosses into `public_api` the way one component imports another, so there is no
crossing to prove a `public_api` entry unused. Archkeel still checks that its module exists and,
when the module declares a non-empty literal `__all__`, that the promised name is exported. An
empty `__all__` is not inspected. A module with no inspected export list and no scanned top-level
class or function of that name is `UNKNOWN`, not a silent pass.
For an unambiguous declared function or class, every resolvable scanned type in its parameters,
return or own public fields must also appear in `public_api`; builtins and external types do not.
Ambiguous same-named bindings and annotation forms the shared type walk cannot resolve are never
guessed (AD-66, AD-70-AD-74).

- **Measurement:** none; declaration records mirror the contract.
- **Determinism:** decoding is deterministic for a valid Contract 2.0 document.
- **Blind spots:** Archkeel does not prove that an outside consumer uses the declaration, and it
  does not enforce types the shared annotation walk cannot resolve.
- **Example:** record `sample.api:load` as a name a consumer outside the package may rely on.

Most class-C entries record a judgment: a responsibility, an intended interface, a path or an
owner that a person decided. Archkeel stores and reports those verbatim. `public_api` is also
validated where its promise reduces to scanned facts: existence, literal exports and resolvable
exposed types. A broader judgment that needs testing becomes a class-D claim bound to an evidence
digest, and its outcome stays HYPOTHESIS, never PASS or FAIL. A judgment that reduces to a fact
visible in one observation belongs in class A instead.

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
- **Example:** on Archkeel itself the top level holds 7 components and 9 edges, and the claim names
  `analyzer` (22 modules, 50 inner edges), `check` (13 and 24) and `ir` (18 and 32), while `cli`,
  `render` and `host` stay below on both. Opening a level for one of them is `archkeel init
  --source <path> --namespace <package>`, which drafts that inside as a contract of its own (AD-20).

`cross-component type fan-in` is the fifth claim (issue #9, AD-59). Its signals are the `symbols`
and `imports` sections: `imports` for which function or method a cross-component call reaches,
`symbols` for that function's own parameter and return annotations. The derivation groups every
crossing function once per ordered component pair it is called across, however many import sites
name it, collects the raw annotation string at every parameter and return position, and names
every annotation string that is passed across two or more distinct component pairs, most-crossed
first.

- **Measurement:** the annotated positions examined, and the candidates beside them.
- **Determinism:** both signals come from one observation and one derivation, so the claim is
  deterministic wherever the analyzer ran; it never becomes a verdict or an exit code.
- **Blind spots:** the annotation is the raw string a function declares, not a resolved type, so
  `Order` from one module and an unrelated `Order` from another are the same candidate; a call
  reached only through a re-export whose chain the scan cannot expand is invisible the way
  `interface_boundary`'s own blind spot is. A type that crosses many boundaries is not itself a
  problem, only the material a broad-context smell would show up in.
- **Example:** on the shop sample `Order` and `str` each cross two component pairs. On Archkeel
  itself `str`, `bool`, `bytes` and `object` are the widest, all builtins or `ir.codec`'s own
  untyped-JSON boundary, and `Observation` and `RunResult` follow at three: Archkeel's shared IR
  model crossing widely is the architecture working as declared, not a service-locator context
  smuggled through a facade, which is the reading the claim leaves to the architect (AD-26).

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
