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
shadowed name still resolves to the shadowing definition first. AD-58 refused "a fixed list that
would drift from what Python actually ships"; `dir(builtins)` is what Python ships and cannot drift
from it. Reporting 79 `str`/`int`/`bool` positions as things the rule could not decide would have
been the very noise AD-26 warns teaches readers to skip a section, and the honest remainder, 69,
is less than half the figure the issue carried.

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
only that the silence now says how large it is.

Limit: the record says how many positions of each undecidable kind there are and not which ones,
so finding a specific undecided position still means reading the facade. `_BUILTIN_NAMES` is the
analyzer interpreter's own builtins, so a position counted as decided on one Python build could be
counted as undecided on another where that name is not a builtin; this is the determinism AD-7
already measures for one machine and Python build, and the analyzer digest (AD-3) keeps two such
runs from being compared. A union (`str | None`) and a mapping (`Mapping[str, str]`) stay
undecidable: entering a union is not the same question as entering a collection, and whether a
`Mapping[...]` is the broad container AD-58 reports a `dict[...]` for is a reading this change does
not settle. `ANALYZER_VERSION` rises to 0.28.0 (AD-3): the same input now yields a record no
earlier analyzer produced, and `fixtures/D-self` is regenerated to match.
Check: `tests/test_analyzer.py::test_boundary_types_reports_a_position_it_could_not_decide` (red on
the pre-fix code: `unknowns` carried no `boundary_type_limit` record at all, and the rule's silence
covered a decided `str`, a dotted `datetime.datetime`, a forward-referenced `'Later'` and an
unannotated parameter alike), together with
`test_boundary_types_reports_unknown_when_the_facade_has_no_subjects`, which fixes the other end
of the same scale, and `archkeel validate --root . --json` still exiting 0 on this repository with
`ANALYZER-TYPES-DECLARED` declared, passing, and now saying how much of `analyzer`'s facade it
decided.
