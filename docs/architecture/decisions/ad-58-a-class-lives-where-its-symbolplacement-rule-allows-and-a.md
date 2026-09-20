# AD-58 A class lives where its symbol_placement rule allows, and a facade's dict or object is all boundary_types decides

The rule kind `symbol_placement`
states that a class of a named kind below `source` is defined only in an allowed module:
`class_kinds` names one or more of `protocol`, `enum`, `pydantic_model`, `dataclass` and `class`,
exactly the five values `class_kind` already resolves through the fixpoint over base classes
`analyzer.embedded.symbols` runs, so the rule is a selector over records the analyzer already
carries, not a new resolver. `allowed_sources` and `exact_sources` name the modules a matching
class may be declared in, matching `forbidden_construct`'s own convention (AD-49): a prefix
allows a module and everything below it, an exact entry only the module itself. A second rule
kind, `boundary_types`, states that a public function below `source` takes and returns no bare
`dict` or `object`: it matches every non-underscore, module-level function in scope and reports
one violation per parameter or return position whose annotation is exactly `dict`, `Dict`,
`object`, or a `dict[...]`/`Dict[...]` generic. Archkeel's own contract adopts
`TYPES-ENUM-IN-MODEL`, a `symbol_placement` rule stating that every enum below `archkeel` is
declared in `archkeel.ir.model`: true today, because every `StrEnum` subclass in this repository,
five of them, already lives in that one module, and the rule keeps it that way.

Reason: issue #9 asked for a third rule, `boundary_types`, deciding whether a facade function's
parameter and return types are declared models, Pydantic models, enums or builtins, the way
`SourceRequest` belongs to `io.api` and nothing else. A parameter or return annotation is recorded
as a string, so deciding what it names means resolving where the name comes from, which AD-37 and
AD-40 leave unfinished for a call's receiver. A throwaway script measured Archkeel's own public
functions and the shop sample's: of 189 annotation positions on Archkeel's own, 123 (65%) are
decidable from the string alone or a lookup inside the same module, a builtin, a bare `dict`,
`Dict` or `object`, a `dict[...]`/`Dict[...]` generic, or a bare name a symbol record in the
function's own facade module already declares. Resolving a bare name through the defining
module's own import bindings, the same mechanism `analyzer.embedded.symbols._resolve_static_name`
already applies to a class's base list, closed most of the rest: 136 of 189 (72%) resolved, 13
more than the string alone gives. But that step proved unsound for the rule as issue #9 phrased
it, "declared in C's facade": `archkeel.analyzer.observe` returns `ObservationResult`, declared in
`ir`'s own facade, not `analyzer`'s; `shop.render.text.render_order` returns `Order`, declared in
`shop.model`'s facade, not `shop.render`'s. Both are the intended provider-owns-the-contract
pattern the issue asks for, and a rule checking only C's own facade would report both as
violations, exactly the false positive AD-26 warns a claim, and by extension a rule, must never
produce.

Rejected: matching a bare name against every component's declared `public` list, not only C's
own, which would clear the `ObservationResult`/`Order` false positives, because deciding which
component a resolved name's own module belongs to is a second derivation this rule would then
carry permanently, and the measurement above still leaves 28% of positions unresolved (a dotted
name, a forward reference, a generic parameter) with no story for them; a rule that decides most
of its cases loudly and the rest by silent omission is worse than a smaller rule that never
guesses. Applying `boundary_types` component-wide instead of behind a `source` selector, because
the same measurement found `archkeel.ir` itself using `object` and `dict[str, RawJson]` 25 times,
in `ir.codec`'s own untyped-JSON boundary and in narrowing helpers such as
`text_value(value: object) -> str`: a component that is a shared model and codec library
legitimately takes `object` at its edges, so the rule needs an architect's own choice of `source`
rather than firing on every component that declares a public interface. Flagging a bare `Any`
alongside `dict`/`object`, because `forbidden_construct: any_annotation` already reports every
`Any` in a parameter, return or variable annotation, and a second rule naming the same occurrence
would duplicate it rather than add a case `any_annotation` cannot see.

Limit: `boundary_types` decides only what the annotation string itself commits to: `dict`, `Dict`,
`object`, and a `dict[...]`/`Dict[...]` generic, whatever its parameters. A named type, a
dotted name, a forward-reference string, `Any`, a generic other than `dict`, and a missing
annotation all stay silent, because deciding any of them needs resolving where the name comes
from and which component's facade owns it, which stays future work. Only a module-level function
is checked, never a method, so `self` and `cls` never enter the question. `symbol_placement`
inherits `class_kind`'s own blind spot: a base resolved through an alias the fixpoint cannot
follow keeps whatever kind it last held. `ANALYZER_VERSION` rises to 0.25.0 (AD-3): a contract may
now yield violation records no earlier analyzer could produce. Check:
`tests/test_analyzer.py::test_symbol_placement_reports_a_class_outside_its_allowed_module`,
`tests/test_analyzer.py::test_boundary_types_reports_a_bare_dict_but_not_a_named_type`,
`tests/contracts/valid/symbol-placement.json` and the two `tests/contracts/invalid/symbol-placement-*.json`
files in `tests/test_contract_model.py`'s corpus and round-trip tests, the demo rows
`class-a-symbol-placement` and `class-a-boundary-types` in `tests/test_architecture_demo.py`, and
`archkeel validate --root . --json` passing with `TYPES-ENUM-IN-MODEL` declared.
