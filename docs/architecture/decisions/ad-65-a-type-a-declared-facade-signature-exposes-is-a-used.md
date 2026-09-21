# AD-65 A type a declared facade signature exposes is a used public entry

## What changes

One notion of `public`, reached two ways. An entry is used when a cross-component import
resolves to it ([AD-9](ad-09-components-declare-their-interface.md),
[AD-56](ad-56-a-public-entry-the-scan-never-saw-is-missing-and-planned.md)) **or** when a
declared facade signature names it.

```
check.public += archkeel.check.ports:Analyzer
$ archkeel validate --root .
exit 2   interface.unused | archkeel.check.ports:Analyzer     # before
exit 0                                                        # now
```

`interface_boundary`'s own reading is untouched, and so is `boundary_types`
([AD-63](ad-63-boundarytypes-reads-a-components-declared-public-list-not-a.md)). What changed is
what counts as *reaching* an entry, in the unused-entry check alone.

## Why

AD-63 measured ten findings in `check` and `render`, and the first answer a reader reaches for
is to declare the type. Declaring one earned `interface.unused` in the same run: `cli` never
imports the name, it passes values through. The rule that asks for a type to be declared and
the check that asks whether declaring it was worth it disagreed about the same position.

The resolution is computed once, by the analyzer, and published as a `facade_types` key on the
facade function's own `symbols` record. `check` reads it. That is AD-4's channel, not a
convenience: `check` reaches the analyzer through a port precisely so it never imports it, and
a second resolution inside `check` would decide the same annotation differently the first time
either improved.

The record is written whether or not a `boundary_types` rule is declared, because the question
belongs to every component with a facade -- otherwise `check` and `render` could not adopt the
rule without already having it.

Measured on `fixtures/D-self`: 64 declared facade functions expose 26 distinct types. Twenty-one
are declared by their owning component. Five are not: the three AD-63 named, plus
`datetime.datetime` and `pathlib.Path`, which belong to no component. No diagnostic anywhere
changed, so no finding was silenced to make an entry legal.

## Rejected

| Alternative | Why not |
|---|---|
| A second list, `exposed_types` | Its own ownership, underscore and namespace checks, plus a rule keeping it in step with `public` -- two lists drift, one cannot (AD-56 rejected `planned_public` the same way). |
| Derive the positions again inside `check` | One piece of knowledge in two places, the defect this repository names most often. |
| Move the resolution into `ir` | Puts rule evaluation in the component whose responsibility is I/O-free derivation, and widens `analyzer`'s `requires` past what AD-4 binds it to. |
| Record every function's annotations, filter in the reader | An internal helper's parameter is not an exposure; the filter is the substance. |
| Count only another component's facade | `run_report` is `check`'s own facade and `Analyzer` is `check`'s own type -- the whole case. |
| Count any import inside the component | An internal import is not an exposure; nearly every entry would read used. |

## Limit

Only a bare identifier resolves, so a type exposed through `list[Widget]` still reads as unused
-- closed later by [AD-69](ad-69-one-annotation-is-read-once-for-both-readers.md). A component
with no `public` records no facade types. `planned` takes no part. The reach is a presence
check, not an attribution: it says a signature exposes the type, not that anyone depends on it,
which is honest -- a facade promising a type has made the promise regardless.
`ANALYZER_VERSION` rises to 0.28.0 (AD-3).

## Check

`tests/test_analyzer.py::test_a_declared_facade_records_the_types_its_signature_exposes` is red
without the key; `tests/test_validation.py::test_public_entry_a_declared_facade_signature_exposes_is_used`
is red with `interface.unused`. `test_public_entry_only_an_internal_signature_names_is_still_unused`
holds the facade filter, and the demo catalog still produces `interface.unused` for a type no
shop facade names.
