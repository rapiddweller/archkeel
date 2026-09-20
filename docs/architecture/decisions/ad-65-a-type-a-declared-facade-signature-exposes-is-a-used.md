# AD-65 A type a declared facade signature exposes is a used public entry

There is one notion of `public` with two ways of being reached, not two declarations. An entry
of a component's `public` list is used when a cross-component import resolves to it, exactly as
[AD-9](ad-09-components-declare-their-interface.md) and
[AD-56](ad-56-a-public-entry-the-scan-never-saw-is-missing-and-planned.md) already read it, *or*
when a declared facade signature names the type it declares: a parameter or return annotation on
a function some component's own `public` list covers exposes that type to every consumer of the
signature, whether or not any consumer imports the name. `interface_boundary`'s own reading is
untouched — an import still has to reach a declared name — and so is `boundary_types`
([AD-63](ad-63-boundarytypes-reads-a-components-declared-public-list-not-a.md)). What changed is
what counts as *reaching* an entry, in `interface_diagnostics`' unused-entry check alone.

The evidence was already collected. `_facade_positions` splits into a rule-independent
`_declared_facade_positions` — is this record a module-level function its own `component.public`
covers, and what are its annotated positions — and the `source`/`allowed_sources`/`exact_sources`
narrowing `boundary_types` puts on top of it (AD-49). `facade_signature_types` walks the first
one for every component that declares a facade and resolves each position with the same
`_resolve_named_type` the rule uses, writing the result as a `facade_types` key on the facade
function's own `symbols` record, beside the annotations it resolves: dotted `module.Name`
origins, sorted, and only when at least one position resolves. `check.validation` reads that key
off the observation and matches it with `_entry_reached_by`, the one predicate that also matches
an import's `reexport_chain`, because both carry the same dotted shape — a `pkg.module:Name`
entry needs the exact name, a `pkg.module` entry any name the module defines. The rule that asks
for a type to be declared and the check that asks whether declaring it was worth it therefore
read one resolution, computed once, and cannot disagree about the same position. The record is
written whether or not a `boundary_types` rule is declared, because the question
`interface_boundary` asks belongs to every component with a facade; if it needed the rule,
`check` and `render` could not adopt the rule without already having it.

That the answer travels in the observation rather than in shared code is AD-4's channel, not a
convenience: `analyzer` publishes signals through `ir.model` and `ir.codec`, and `check` reaches
the analyzer through a `ScanConfig`/`Analyzer` port precisely so it never imports it. A
`facade_types` key costs no schema change, since a record's `data` payload is open by
[AD-2](ad-02-json-has-one-type.md) and the common schema validates no key of it; it costs
`ANALYZER_VERSION` 0.27.0 → 0.28.0 ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)),
because a scan may now yield a record no earlier analyzer could produce, and `fixtures/D-self` is
regenerated to match.

Reason: issue #57, reproduced on this repository before anything changed. AD-63 measured ten real
findings in `check` and `render` — a `Analyzer`/`Host` Protocol in `archkeel.check.ports` that six
of `check`'s declared facade functions take as a parameter, and a `Summary` dataclass in
`archkeel.render.summary` that four of `render`'s return or take — and the answer a reader of such
a violation reaches for first is to declare the type. Declaring one gave:

```
check.public += archkeel.check.ports:Analyzer
$ archkeel validate --root . --json
exit 2
  inside.public_mismatch | check
  interface.unused       | archkeel.check.ports:Analyzer
```

Two diagnostics, and only one of them is this issue. `inside.public_mismatch` is
[AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)'s and
[AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)'s ordinary requirement that
a level and its inside declare one public surface: `check` has an inside, the entry was added to
the outer contract alone, and repeating it in `foundation`'s own `public` in
`src/archkeel/check/architecture-contract.json` clears it. It is bookkeeping the reproduction
omitted, not a collision between two rules, and it is not in scope here. With the inside kept in
step, the reproduction reduced to the one diagnostic this decision is about, and declaring all
three types gave three of them: `exit 2`, `interface.unused` for `archkeel.check.ports:Analyzer`,
`archkeel.check.ports:Host` and `archkeel.render.summary:Summary`. `cli` imports none of the
three; it passes a concrete analyzer into `run_report` and reads a `Summary` only as what a
`*_summary` call returns, so each name appears only as a signature type. The declaration that
satisfied `boundary_types` was immediately called unused by `interface_boundary`, and the ten
findings could be answered only by changing the signatures or by leaving the rule undeclared —
which is what AD-63 did, and why its dogfooding stopped at `analyzer`.

After this change, the same three declarations (in both contract levels) give
`archkeel validate --root . --json` at `exit 0` with zero diagnostics.

Measured on the regenerated `fixtures/D-self`, which declares none of them: 64 declared facade
functions below `archkeel` carry a `facade_types` key, exposing 26 distinct types. Twenty-one are
declared by their own owning component's `public` list, which is what AD-63 already found the
common case to be. Five are not: the three AD-63 named, and `datetime.datetime` and `pathlib.Path`,
which belong to no declared component (`component_for` returns `None`) and so can never match a
`public` entry, since `reference.public_owner` and the namespace check keep every entry inside the
scanned namespace. No diagnostic anywhere in the repository changed: `validate` reported zero
before this change and zero after, so no finding was silenced to make the entry legal, and the
demo catalog's `validation-interface-unused` row still produces `interface.unused` for
`shop.model.entities:Discount`, a type no shop facade signature names.

The two measurements say the preferred answer holds. One notion with two ways of being reached
needs one list, one resolution and one matching predicate; a second `public`-like list, with its
own consistency rule between the two, would have to be kept in step by hand for exactly the
positions the analyzer already resolves. Nothing in the evidence argued for the second reading:
the collision was never that the two rules mean different things by `public`, only that
`interface_boundary` counted one of the two ways a name reaches a boundary.

Applied to Archkeel: nothing is declared. `archkeel.check.ports:Analyzer`,
`archkeel.check.ports:Host` and `archkeel.render.summary:Summary` stay out of `public`, and
`check` and `render` stay without a `boundary_types` rule. Declaring them by hand would fail
`tests/test_self.py::test_self_contract_public_matches_drafted_proposal`, the SPOT guard AD-54
already ran into, which holds `architecture-contract.json`'s `public` lists to exactly what
`init`'s `draft_contract` proposes from the observation; `draft_contract` proposes an entry from
observed cross-component *imports*, and none of the three has one. Making the draft see a facade
signature is a change to `init`'s drafting, and adopting `boundary_types` for two more components
is a decision about their ten findings. Both belong to issue #61, which this decision unblocks and
does not pre-empt: `tests/test_self.py::test_self_facades_record_the_ten_types_they_expose` asserts
both halves — that the three types are recorded as reached, and that none of them is declared yet.

Rejected: a second declaration beside `public`, say `exposed_types`, which the issue named as the
alternative. It needs its own ownership, underscore and namespace checks, its own diagnostic for
an entry `public` has never heard of, and a rule keeping the two in step, all to record something
`boundary_types` already derives from the code; AD-56 rejected `planned_public` in the same shape
and for the same reason, that two lists can drift and one cannot. Deriving the facade positions a
second time inside `check.validation`, which has the `symbols` and `imports` sections and could
rebuild the import-binding index, the class index and `_facade_covers` from them: that is the
defect this repository names most often, one piece of knowledge in two places, and the two copies
would decide the same annotation differently the first time either resolution improved. Moving the
resolution into `ir` for both components to import, which would widen `analyzer`'s `requires`
entry past the two modules AD-4 binds it to and put rule evaluation in the component whose
responsibility is I/O-free derivation. Recording every function's resolved annotations rather than
only a declared facade's, leaving the facade filter to the reader: an internal helper's parameter
type is not an exposure to another component, so the filter is the substance of the answer, and
splitting it from the resolution would let the reader apply a different one. Counting only another
component's facade signature, not the declaring component's own: `run_report` is `check`'s own
facade and `Analyzer` is `check`'s own type, which is the whole case, and a rule that excluded it
would leave issue #57 exactly where it found it. Widening `_entry_used` further, so that any
import inside the component counts — `check.report` does import `Analyzer` from `check.ports` —
because an internal import is not an exposure at the boundary and that reading would mark nearly
every entry used, retiring `interface.unused` by accident.

Limit: only a bare identifier resolves, so the unresolved bucket AD-63 measured at 58% of
positions is unchanged in kind here — a dotted name, a subscripted generic, a forward-reference
string, a missing annotation and a builtin resolve to nothing, reach nothing, and are recorded as
nothing; a type exposed only through `list[Widget]` still reads as unused. A component that
declares no `public` has no facade functions, so it records no facade types, the same blank AD-63
gives it. `planned` (AD-56) takes no part, because it is never projected into the observation.
`interface.missing` is untouched: a facade type resolves only to a module the scan read, so an
entry naming an unscanned module cannot be reached this way. The reach is a presence check, not an
attribution: `facade_types` says a signature exposes the type, not which component's consumer
depends on it, so an entry reached only this way is not evidence that anybody outside uses it —
which is the honest reading, since a facade promising a type in its signature has made the promise
regardless. And the key is written only where something resolves, so absence does not distinguish
a facade function whose annotations all stayed unresolved from a function that is not facade at
all; nothing asks that question of this field, and `rule_subject_failures` answers the facade-set
question from the same predicate instead. Check:
`tests/test_analyzer.py::test_a_declared_facade_records_the_types_its_signature_exposes` (red on
the pre-fix code: no `facade_types` key existed) and
`test_an_unresolved_facade_annotation_records_no_type` for the limit;
`tests/test_validation.py::test_public_entry_a_declared_facade_signature_exposes_is_used`, red on
the pre-fix code with `interface.unused` on `sample.core.ports:Widget`, and
`test_public_entry_only_an_internal_signature_names_is_still_unused` holding the facade filter;
`tests/test_self.py::test_self_facades_record_the_ten_types_they_expose` on this repository's own
observation; `tests/test_validation.py`'s `test_unused_public_entry_is_a_diagnostic`,
`test_missing_public_entry_is_a_diagnostic` and the three `planned` tests passing unchanged; and
`archkeel validate --root . --json` exiting 0 on Archkeel's own contract.
