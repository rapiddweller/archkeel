# AD-67 An undecidable boundary position is UNKNOWN, not silence

`boundary_types` produced a record only when it had a violation to report. Every other position
produced nothing at all, so the rule alone read `no violation == probably fine`, where the rest of
this tool reads PASS as proven fine, VIOLATION as proven wrong and UNKNOWN as could not be decided.
AD-26 settled that shape for a quality claim -- a derivation without its signal reports UNKNOWN and
shows no candidates, because "a claim whose candidates are wrong every time teaches readers to skip
the section" -- and AD-63 extended `rule-without-subjects` to the case where this rule decides
*nothing*. What was left was the middle: a rule that decided some of its positions and stayed
silent about the rest, with no number anywhere saying which was which.

`_boundary_type_reason` is the mechanism that made the two indistinguishable. It answered `None`
for a decided pass, for a name it could not resolve, for a dotted name, for a generic, for a
forward reference and for a type owned by no declared component alike. It becomes
`_boundary_type_verdict`, returning a `_Position` of a violation reason, an undecidable kind, or
neither -- neither being a decided pass. `boundary_type_limits` then walks the same
`_facade_positions` list `_boundary_types_violations` walks, and files one UNKNOWN record per
`boundary_types` rule in `unknowns`: `positions` seen, `decided`, `undecided`, and a count for each
undecidable kind. That is the shape `dynamic_call_limit` already gives the call graph (a
denominator and the part of it that stayed unresolved) rather than a third mechanism, and it is
AD-26's own rule for a denominator the analyzer cannot compute otherwise: report what was examined
instead of inventing the rest. A position with no annotation at all is now carried into that list
with an empty annotation string instead of being dropped, because a parameter nobody annotated is a
part of the facade this rule could not decide, and dropping it hid it from the rule's own
denominator.

This reports; it does not gate. The record is filed in `unknowns` and never in
`coverage.failures`, so `coverage.rules` stays `PASS`, no `Diagnostic` is raised, and the exit code
does not move. The line is: a rule that decided nothing at all has no verdict and is already gated
by `rule-without-subjects` (AD-63, issue #56); a rule that decided some of its positions has a
verdict those positions earned, and the remainder is an analysis limit of exactly the kind
`dynamic_call_limit` has never gated on. Gating here would make every generic and every external
type in any facade a build failure, which is pressure to delete annotations rather than to declare
types -- the opposite of what the rule is for. What changes is what a reader is told: `report` now
prints, under Known unknowns, how much of each facade the rule actually decided.

Reason, measured on this commit against Archkeel's own `architecture-contract.json`, with a
`boundary_types` rule widened to `source: archkeel` so the whole namespace is in view (the declared
`ANALYZER-TYPES-DECLARED` rule is scoped to `archkeel.analyzer` and sees 8 positions of it): 88
declared facade functions carry **258 positions**. Under AD-63's code, **36** of those produce a
violation (26 a bare `dict`/`object` in `ir.codec` and its narrowing helpers, 10 the
`Analyzer`/`Host`/`Summary` types AD-63 already named) and **222 produce silence**. Of those 222,
**153 are decided passes** -- 79 a builtin, 74 a name resolving to a type its own component's
`public` list declares -- and **69 (27% of all positions) are genuinely undecidable**: 41 a
subscripted generic, 17 a union, 10 a type owned by no declared component, 1 a bare name nothing
resolves (`StructureLevel`). Zero dotted names, zero forward references and zero unannotated
positions occur in Archkeel's own facades. On the shop sample (`fixtures/F-architecture`, rule
widened to `source: shop`): 3 facade functions, 10 positions, 3 decided by name, 6 builtin, 1 a
type owned by no component -- 1 undecidable of 10.

Issue #59 quotes 94 resolved and 146 (58%) undecidable, AD-63's own Limit the same. Re-measuring
those numbers is what forced the one reading this decision had to settle: 79 of that 146 are a
bare builtin, and issue #9's own phrasing names "Pydantic models, enums or builtins" as acceptable
boundary types, so a builtin is proven fine, not undecided. A builtin needs no import and defines
no symbol of its own, so `_resolve_named_type` returns nothing for one, which is why AD-58 and
AD-63 could not tell it apart from a failure to resolve. `_BUILTIN_NAMES` is `dir(builtins)`, asked
of the running interpreter after the imports and the module's own classes have been tried, so a
shadowed name still resolves to the shadowing definition first. That set is asked of the
interpreter rather than kept as a list in this file, because `resolve.py` and `calls.py` already
answer the same question the same way, and a second list of builtin names would be a second thing
to keep in step with the language. Reporting 79 `str`/`int`/`bool` positions as things the rule could not decide would have
been the very noise AD-26 warns teaches readers to skip a section, and the honest remainder, 69,
is less than half the figure the issue carried.

The second change closes the sharpest case the reporting exposed: the same mistake disappeared by
being wrapped. `def execute(context: InternalContext)` was reported and
`def execute(contexts: list[InternalContext])` was silent, because a generic's parameters were
never inspected, so anybody refactoring a parameter into a list dropped the check without a word
anywhere. `_collection_verdict` decides `Container[Name]` when the container is one of the known
collections (`list`, `tuple`, `set`, `frozenset`, `Sequence`, `Iterable`, `Iterator`, `Collection`,
`AbstractSet` and their `typing` spellings) by running the same `_boundary_type_verdict` on each
type parameter -- the resolution `boundary_types` already performs on a bare name, applied one
level in. A collection is only as decided as its parameters: one violating makes the position a
violation, otherwise one undecidable makes it undecidable, and only all of them deciding clean
makes it a pass. `enter_collections=False` on that inner call is what keeps it one level and not
name resolution in general, so a nested subscript stays undecidable, and a dotted name, a forward
reference and an external type inside a collection stay undecidable for their own reason --
`list[datetime.datetime]` is now counted as a dotted name rather than as a generic, which is the
truer answer. `dict`/`Dict` are deliberately not collections here, because AD-58 already reports a
`dict[...]` as the broad container it is, and `Mapping` is left out because whether a mapping is
that same broad container is a separate reading.

Measured, on the same commit and the same widened `source: archkeel` rule: the undecidable 69 falls
to **38 (15% of 258)** -- generics from 41 to 9, unions 17 to 18 (`tuple[RunResult, bytes | None]`
is now undecidable for its element's union rather than for being a generic), the 10 external types
and the 1 unresolved name unchanged -- and the violations rise from 36 to **39**. All three new
ones are real and none is a false positive: `archkeel.ir.levels.inside_levels` returns
`tuple[InsideLevel, ...]` where `ir` never declared `InsideLevel`, and
`archkeel.check.onboarding.run_init` and `archkeel.check.validation.run_validate` both return
`tuple[RunResult, dict[str, bytes]]`, a bare `dict[...]` crossing `check`'s facade inside a tuple.
All three are exactly the refactoring hole: the same finding the rule already reports unwrapped.
On the shop sample nothing changes at all -- its three facade functions carry no generic in any
position -- so the evidence for this step is Archkeel's own 31 positions moved from undecidable to
decided and those 3 findings, not the sample. Applied to Archkeel's own contract, nothing moves:
`ANALYZER-TYPES-DECLARED` is scoped to `archkeel.analyzer`, whose one facade function's
`tuple[str, ...]` decides clean on a builtin, so `archkeel validate --root . --json` still exits 0
with no diagnostics. The three findings sit in `ir` and `check`, which AD-63 already left
unadopted, and they join the `Analyzer`/`Host`/`Summary` list it opened rather than starting a new
one.

Rejected: filing the record in `coverage.failures` beside `rule-without-subjects`, which would
have made it a `rule_without_subjects` diagnostic and exit 2 -- on this repository that is a run
failed by 41 tuples and 10 `Path` parameters, none of which is a finding, and a gate nobody can
clear by declaring anything is a gate that gets deleted. One UNKNOWN record per undecidable
position, which reads closer to the issue's wording and is what a violation does, rejected because
146 rows on the one measured repository, most of them `tuple[str, ...]`, is the section-skipping
failure mode AD-26 names, and because what a reader needs from an undecided position is its size
and its kind, not its identity: the annotation is already in the source at the qualified name the
rule inspected. A `coverage` field of its own, the way `calls_unresolved` sits on `Coverage`,
rejected because `Coverage` speaks about the scan -- files discovered, files parsed, calls
analyzed -- and is computed before rules are evaluated; how much of a facade one declared rule
decided is a property of that rule, and it belongs where the rule's id can be carried on the
record. Counting an undecidable position as a violation, never seriously: it is exactly the
"guessing would be worse than staying silent" AD-63's Limit records, and this decision changes
only that the silence now says how large it is. Descending through a collection's parameters
recursively rather than one level, rejected because a nested subscript is a second question --
whether `tuple[tuple[str, tuple[str, ...]], ...]` is a boundary type at all -- and because one
level is what the measurement covers: 31 of the 41 undecided generics on this repository are one
level deep, and the 9 that are not stay undecidable and say so. Entering a mapping alongside the
collections, rejected because `Mapping[str, str]` raises AD-58's own question about a broad
container, which this decision does not answer; it stays undecidable, which is what it is.

Limit: the record says how many positions of each undecidable kind there are and not which ones,
so finding a specific undecided position still means reading the facade. `_BUILTIN_NAMES` is the
analyzer interpreter's own builtins, so a position counted as decided on one Python build could be
counted as undecided on another where that name is not a builtin; this is the determinism AD-7
already measures for one machine and Python build, and the analyzer digest (AD-3) keeps two such
runs from being compared. A union (`str | None`), a mapping (`Mapping[str, str]`), a
nested subscript, a dotted name, a forward reference and a type no component owns all stay
undecidable, 38 positions of 258 on this repository: entering a union is not the same question as
entering a collection, and none of the rest resolves to a `(module, name)` this rule can judge.
`ANALYZER_VERSION` rises to 0.28.0 for the limit record and 0.29.0 for the collection element
(AD-3): each step makes the same input yield records the other does not, and `fixtures/D-self` is
regenerated after each.
Check: `tests/test_analyzer.py::test_boundary_types_reports_a_position_it_could_not_decide` (red on
the pre-fix code: `unknowns` carried no `boundary_type_limit` record at all, and the rule's silence
covered a decided `str`, a dotted `datetime.datetime`, a forward-referenced `'Later'` and an
unannotated parameter alike) and
`test_boundary_types_decides_a_bare_name_inside_a_collection` (red on the step-one code: the
wrapped `list[Payload]` and `set[Payload]` produced no violation at all), together with
`test_boundary_types_reports_unknown_when_the_facade_has_no_subjects`, which fixes the other end
of the same scale; the demo row `class-a-boundary-types-in-collection` in
`fixtures/demo_catalog_types.py`, regenerated into `docs/architecture-demo.md`; and `archkeel
validate --root . --json` still exiting 0 on this repository with `ANALYZER-TYPES-DECLARED`
declared, passing, and now saying how much of `analyzer`'s facade it decided.
