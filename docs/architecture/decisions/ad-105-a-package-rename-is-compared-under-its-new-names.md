# AD-105 A package rename is compared under its new names

`validate --against <ref>` compares the contract at `ref` with the one validated field by field
(AD-61). A rename changes every field that names the package, so a rename that widens nothing
read as dozens of widenings, and a `public` entry it replaced was not even listed as lost (#151).

Now the component packages that moved propose a prefix substitution: `shop.render -> shop.view`,
or `window_cleaning_mobile -> field_service_mobile` with `...features.kunde ->
...features.customer` beside it. A pair drops the trailing segments the move kept, and a
component's moved packages pair by the last segment only one of each side has, then in order.
When the substitution holds, the old contract and, with `--baseline`, the old baseline are
renamed with it before `ir.widening` compares them. The JSON result lists it as `renames` (`null`
when no revision was compared) and the terminal names each line. Whatever it does not explain is still
compared, so a real widening beside a rename fails alone.

| `validate --against`, same input on `main` and now | `main` | Now |
|---|---:|---:|
| shop sample: `shop.render` moved to `shop.view`, its import and the contract | 12 failures | 0, exit 0 |
| the same, and one gained `allowed_sources` entry | 13 | 1: that entry |
| G-dart: package `shop -> field_shop` (pubspec, namespace, imports), `lib/presentation -> lib/ui` | 21 | 0, exit 0 |
| shop sample: `shop -> store_app`, scan roots and namespace included | 85 | 1: the moved `inside` path |
| Archkeel itself: `archkeel.host -> archkeel.hosting`, with its baseline | 5 | 0, exit 0 |

## When a substitution holds

`ir.renames.rename_holds` decides from names alone, and each clause has a test that fails
without it:

- Every prefix relation among the dotted names the old contract and baseline hold survives: one
  name held another before exactly when their new names hold each other. A rule, package or
  entry scopes by prefix, so the renamed contract then states for each new name what the old
  stated for its old name. This rejects two names becoming one, a grant the old contract gave
  `shop.view` passing to the renamed code, a rule on `shop` that stops covering it, a rule on
  `other` that starts, and two unrelated packages that would nest and so overlap.
- No module the scan reads keeps an old name: copied code would be governed by nothing.

Every dotted string in any field counts as a name, so a later field is renamed with no list to
keep; prose, paths and URLs never match. Where the code moved differently from the contract,
two packages trading places say, the change is a code move between components, which `--against`
has never judged.

## Rejected

- Scanning the compared revision to prove where each module went: its snapshot holds Python
  files only, so the issue's Dart case would never be recognised, and two packages holding the
  same module names still could not be told apart.
- A rename line that still needs an amendment: the reviewer would redo the check by hand.
- Taking gained and lost entries with matching tails as the rename: without the clauses that
  is the heuristic that hides a widening. It is kept as display only, where no rename holds:
  `component 'api'.public gained 'b.api.x' in place of 'a.api.x'` still fails as before.
- A clause on `[scan] namespace`: every name of the new contract must lie in the new namespace
  (exit 2 otherwise) and the scan names modules under it, so a namespace the substitution does
  not explain leaves a difference that is still compared.

## Limits

- Paths are not renamed. A moved `inside` contract stays one finding: `--against` does not
  compare what an inside holds, so its path is all that records which inside the level trusts.
- A label, id or other word spelled like a renamed package is renamed too, and reported where
  the new contract kept it.
- A package that is added, dropped or split in the same change is not a move: the rename is
  recognised from the others, and that component's change is compared as before.

## Tests

`tests/test_renames.py`; `tests/test_architecture_demo.py` runs `against-package-renamed`,
`against-package-renamed-widened` and `dart-against-package-renamed`.
