# AD-63 boundary_types reads a component's declared public list, not a naming convention

AD-58 gave `boundary_types` a facade definition of its own: "public" meant a Python name that
does not start with an underscore, on a module-level function under `source`, with no reference
to `component.public` at all. Under that definition, resolving a bare annotation name through the
same import-binding mechanism `symbols._resolve_static_name` already applies to a class's base
list closed most of the string-alone gap -- 136 of 189 positions (72%) resolved, 13 more than the
104 decidable from a builtin, a bare `dict`/`Dict`/`object`, a `dict[...]`/`Dict[...]` generic or a
name a symbol record in the function's own module already declared. But 11 of those 13 newly
decidable cases were false: `archkeel.analyzer.observe` returning `ir`'s own `ObservationResult`,
`shop.render.text.render_order` returning `shop.model`'s own `Order`. AD-58 read both as leaks and
rejected the resolution step, restricting the rule to a bare `dict`/`Dict`/`object` and recording
that Archkeel could not adopt `boundary_types` against itself without exempting `ir.codec`'s
legitimate 25 `object`/`dict[...]` uses too.

That measurement was sound. Its conclusion was not, because the two are false positives of the
naming-convention reading alone, not of resolving a name in general. Issue #9 asked whether a
facade function's types are "declared in C's facade, or Pydantic models, enums or builtins" --
`ObservationResult` and `Order` are declared, just not in the calling component's own facade: `ir`
declares `ObservationResult` (`archkeel.ir.model`, a whole-module `public` entry with no `__all__`
to narrow it), and `shop.model` declares `Order` (`shop.model.entities`, in its own `__all__`).
Issue #44 traces the gap: AD-58 checked resolved names against the annotation's own module's
declarations, never against `ContractComponent.public`, so the rule had no way to see that a
provider returning its own declared type is exactly the pattern issue #9 asked for. AD-58's own
Rejected section came within one step of this: "matching a bare name against every component's
declared public list, not only C's own... would clear the `ObservationResult`/`Order` false
positives," and rejected it as "a second derivation this rule would then carry permanently." It is
not a second derivation. `interface_boundary` (AD-9) already resolves exactly this question --
does a `(module, name)` pair fall inside some component's declared `public`, honoring its
`__all__` -- for every cross-component import; `_interface_allows` in
`analyzer.embedded.violations` is the one place that answer is computed. `boundary_types` had
simply never called it.

The fix is two changes to `_boundary_types_violations`, both reusing that existing resolution
rather than writing a second one. First, which functions the rule inspects at all: `_facade_positions`
now requires `component.public` (via `_facade_covers`, factored out of `_interface_allows` as
`_exports_by_module` plus a shared `_facade_covers` helper both rules call) to cover the function's
own `(module, name)` -- a naming convention over every non-underscore, module-level function used
to decide this before, so an internal helper the contract never promised as facade, declared
public or not, fell out of scope entirely. Second, what a resolved named type decides:
`_resolve_named_type` resolves a bare identifier through the same `binding`/`origin_definition`
fields `imports` already carries for `interface_boundary` (a `from ir import ObservationResult`
import's own record, or a same-module class definition when no import is needed), then
`_boundary_type_reason` clears the position when the resolved type's `class_kind` is `enum` or
`pydantic_model`, or when `_facade_covers` finds it in *its own* owning component's `public` list
-- whichever component that is, not only the function's own. Only that last check is new; the
lookup itself (`contract.component_for`, `_facade_covers`) is the same one `interface_boundary`
already runs on every cross-component import. A dotted name, a subscripted generic, a
forward-reference string and a missing annotation stay unresolved and silent, exactly as AD-58
left them: only a bare identifier is attempted, and a builtin needs no import and defines no
symbol of its own, so it resolves to nothing and is never matched against a list that would drift
from what Python ships.

Two edge cases fall out of reusing `_facade_covers` rather than inventing a third reading.
A component that declares no `public` at all (`component.public is None`) has no declared facade
for the rule to read, so none of its functions are inspected -- the same "no interface decision"
that `interface_boundary` and AD-50's `agent_decisions` already give a blank `public`, not a wider
default that would make every helper of an undeclared component a facade function by omission.
A `planned` entry (AD-56) plays no role here, for the same reason it plays none in the analyzer at
all: `planned` is never projected into the observation, so `_facade_covers`, which reads only
`component.public`, cannot see it and does not need to -- a function whose facade is only
`planned` is not yet a fact the scan can check, exactly as AD-56 designed it to be.

The re-run measurement, on Archkeel's own `fixtures/D-self` observation and its own
`architecture-contract.json`: under the naming-convention reading, 610 annotation positions on
every non-underscore module-level function below `archkeel`, 46 of them a bare `dict`/`object`.
Under the declared-facade reading, only 88 functions across five components are facade functions
at all, carrying 258 positions -- 26 still a bare `dict`/`object` (all in `ir`, the same codec
boundary AD-58 already named), and 94 a bare name that resolves. Of those 94: 0 are an enum or a
Pydantic model by kind; 74 (79%) are declared by their own owning component's `public` list --
`ObservationResult`, `Order`, and 72 more, every one of them a provider returning or accepting its
own declared type, the pattern AD-58's measurement mistook for a leak; and 10 (11%) name a type
neither builtin, enum, Pydantic model, nor declared anywhere -- a real `Analyzer`/`Host` Protocol
in `archkeel.check.ports` that six of `check`'s own declared facade functions take as a parameter
without `check`'s `public` list naming it, and a `Summary` dataclass in `archkeel.render.summary`
that four of `render`'s declared facade functions return or take the same way. Zero false
positives turned up in this corpus: every one of the 10 is a type that genuinely crosses a
component's declared boundary without the contract saying so. Against AD-58's own 13-newly-decided,
11-false ratio, this is the reverse: 94 newly decided, 10 true, 0 false -- the numbers the
declared-facade reading was expected to produce if issue #9's phrasing, not AD-58's naming
convention, is the right definition of facade. (AD-64 landed between this measurement's two runs
and moved `ir.baseline`'s `public` entry from four symbol entries to one whole-module entry; the
denominators above are the second run's, on top of it, and the shape of the result did not move:
still 0 false positives, still the same 10 true ones, `check` and `render` unaffected.)

Applied to Archkeel: `ANALYZER-TYPES-DECLARED` (`boundary_types`, `source: archkeel.analyzer`) is
declared in `architecture-contract.json` and passes at 0 violations -- `analyzer`'s one facade
function, `observe`, returns `ir`'s own `ObservationResult` and that is now read as the declared
pattern it is, not a leak. `check` and `render` are not scoped by this rule: both surfaced a real,
uncompensated gap above (`Analyzer`/`Host`, `Summary`), and declaring those two components' own
Protocol and dataclass types public is a real widening of Archkeel's contract that this issue does
not make on the architect's behalf -- reporting it here is the finding issue #44 asked for instead
of a compensating `allowed_sources` list, which would have hidden the same gap `ir.codec`'s bare
`object` already needs one exemption for, not fixed it. Declaring `Analyzer`/`Host` public was
tried and reverted: `cli` never imports either name directly, only as a parameter type, so
`interface_boundary` calls the new entry unused the moment `check`'s own `public` declares it --
a contract-model conflict between two notions of "public", now issue #57, and adopting
`boundary_types` for `check` and `render` is blocked on it, not on judgement. That sentence is
history: [AD-65](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md) made a type a
declared facade signature exposes a used entry, reusing this rule's own resolution, so the
declaration is legal now and the ten findings are open on judgement alone (issue #61). `check`
and `render` still declare neither the three types nor the rule; read AD-65 for the current
state of what "used" means. `archkeel.api`
(AD-64) is not scoped
either, and no sibling rule is declared for it: its component-level `public` is `None` -- the
module's own `__all__` names three exports, but that is Python's own promise, not the contract's,
and AD-64 declared no `public` list for the component in the contract sense -- so under the same
"a component that declares no public has nothing to inspect" reading this decision gives every
other component, a rule scoped to `archkeel.api` would check nothing and pass by construction, not
by evidence. Declaring `archkeel.api`'s contract-level `public` to match its own `__all__` would
make such a rule honest; that declaration is AD-64's own to make, not this issue's.

Rejected: exempting every `dataclass` `class_kind`, not only `enum` and `pydantic_model`, which
would have cleared the `Summary` case along with the two, because issue #9's own phrasing names
"Pydantic models, enums or builtins" and nothing else, and `Summary` is exactly the shape the rule
should catch -- a plain dataclass nobody declared, crossing a facade boundary regardless. Widening
`boundary_types` to every component below `archkeel` in the same change that fixed the reading,
because `ir`'s 26 legitimate `object`/`dict[...]` uses and `check`/`render`'s 10 undeclared types
are two different kinds of debt this issue did not sign up to clear; `source` still lets an
architect scope the rule to the one component whose facade is ready, exactly as AD-58 designed it
to. Checking a resolved name only against the calling function's own component, the reading AD-58
shipped, because that is the naming-convention mistake issue #44 reports, kept for continuity with
nothing gained: the same 11 false positives AD-58 already measured would return.

A second review (issue #56) found the narrowing's own edge, reproduced on this branch:
`archkeel.api`'s own component declares no `public` at all, so a hypothetical `boundary_types`
rule scoped to it -- `source` matching a real, scanned module -- would inspect zero functions and
`archkeel validate` would report a clean pass: `exit 0`, `declared_rules PASS`,
`violations_by_rule []`. Before this decision, the same rule inspected every non-underscore
function under `source`, so the narrowing itself, not merely the widening, introduced a rule that
can only pass by finding nothing to check -- the same defect a declared rule that cannot fail is
everywhere else in this tool. `rule_subject_failures` already reports a rule whose scope selector
matches no scanned module as `rule-without-subjects`, UNKNOWN rather than PASS; it is extended,
not duplicated, for `BoundaryTypesRule`: instead of counting `module_names` against `rule.source`,
it counts the modules `_facade_positions` -- the identical predicate `_boundary_types_violations`
itself evaluates each function against -- actually returns a position list for, so "did this rule
find a subject" and "did this rule actually inspect that subject" read the same predicate and
cannot drift apart. `exports_by_module` (the `__all__` lookup AD-9 already shares between
`interface_boundary` and `boundary_types`) moved from a private, `rule_violations`-only helper to
a public one `scan_repository` computes once, after `symbols` and `module_facts` exist, and hands
to both `rule_violations` and the now-later-running `rule_subject_failures`. Coverage stays a
presence check, not a degree one: this fix answers "did `boundary_types` decide anything at all",
not "how many of its positions did it see, decide or leave unresolved" -- a `calls_unresolved`-
shaped counter for this rule kind is more machinery than a false-pass regression needs, and issue
#59 already covers the unresolved-position half of that question; left to it rather than built
here on the strength of one regression fix.

Limit: the unresolved bucket is unchanged in kind, only in proportion -- 146 of 252 positions
(58%) stay silent below `archkeel`, a dotted name, a subscripted generic, a forward-reference
string, a missing annotation, a builtin, or a type from a module outside every declared component
(`origin_component is None`), because none of those resolve to a `(module, name)` this rule can
judge, and guessing would be worse than staying silent. `check`'s six `Analyzer`/`Host` positions
and `render`'s four `Summary` positions are real, named findings this change reports rather than
silences with `allowed_sources`; they stay open until an architect declares those types public or
decides otherwise. `ANALYZER_VERSION` rises to 0.27.0 (AD-3): a contract may now yield violation
records no earlier analyzer could produce, and `fixtures/D-self` is regenerated to match. Check:
`tests/test_analyzer.py::test_boundary_types_checks_only_the_declared_facade`,
`test_boundary_types_reports_a_type_the_facade_does_not_declare`,
`test_boundary_types_is_silent_when_the_facade_declares_the_named_type`,
`test_boundary_types_is_silent_for_a_provider_returning_its_own_declared_type` (the
`ObservationResult`/`Order` case by name), `test_boundary_types_is_silent_for_an_enum_even_when_undeclared`
and `test_boundary_types_reports_unknown_when_the_facade_has_no_subjects` (issue #56, red on the
pre-fix code: `unknowns` carried no `rule-without-subjects` record and `coverage.rules` read
`PASS` for a rule that inspected nothing);
the demo rows `class-a-boundary-types` and `class-a-boundary-types-declared-type` in
`fixtures/demo_catalog_types.py`, regenerated into `docs/architecture-demo.md`; and `archkeel
validate --root . --json` exiting 0 on this repository, honestly, with `ANALYZER-TYPES-DECLARED`
declared and passing.
