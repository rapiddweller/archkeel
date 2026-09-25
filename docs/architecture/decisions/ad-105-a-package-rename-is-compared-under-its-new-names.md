# AD-105 A package rename is compared under its new names

`validate --against <ref>` compares the contract at `ref` with the one validated field by field
(AD-61). A rename changes every field that names the package, so a rename that widens nothing
read as dozens of widenings, and a `public` entry it replaced was not even listed as lost (#151).

Now the component packages that moved propose a prefix substitution: `shop.render -> shop.view`,
or `window_cleaning_mobile -> field_service_mobile` with `...features.kunde ->
...features.customer` beside it. A pair drops the trailing segments the move kept; a component's
moved packages pair by the last segment only one of each side has, and a single one left on each
side pairs too. When a substitution holds, the old contract and, with `--baseline`, the old
baseline are renamed with it before `ir.widening` compares them. The JSON result lists it as
`renames` (`null` when no revision was compared) and the terminal names each line. Whatever it
does not explain is still compared, so a real widening beside a rename fails alone.

| `validate --against`, same input on `main` and now | `main` | Now |
|---|---:|---:|
| shop sample: `shop.render` moved to `shop.view`, its import and the contract | 12 failures | 0, exit 0 |
| the same, and one gained `allowed_sources` entry | 13 | 1: that entry |
| G-dart: package `shop -> field_shop` (pubspec, namespace, imports), `lib/presentation -> lib/ui` | 21 | 0, exit 0 |
| shop sample: `shop -> store_app`, scan roots and namespace included | 85 | 1: the moved `inside` path |
| Archkeel itself: `archkeel.host -> archkeel.hosting`, with its baseline | 5 | 0, exit 0 |

## What is renamed

Only the module and symbol fields `ir.model.module_references` lists, one list: never an id,
label, kind, `decided_by` or construct, so root `agent` renamed `architect` still reports each
flipped `decided_by`. A baseline's subjects, roles and accepted names are renamed, except a
component cycle's labels. `validate` holds the same list to the scan namespace, which adds a
component `namespace`, `forbidden_construct` sources, `root_layout`, boundary allowances,
commands, path steps and compat modules to that check, as docs/rules.md already stated.

## When a substitution holds

`ir.renames.rename_holds` decides from names; each clause has a test that fails without it:

- Every prefix relation among the old contract's and baseline's names and the renamed prefixes
  survives: one held another before exactly when their new names hold each other. Rules,
  packages and entries scope by prefix, so the renamed contract then states for each new name
  what the old stated for its old one. This rejects two names becoming one, a grant given to
  `shop.view` passing to the renamed code, a rule on `shop` that stops covering it or one on
  `other` that starts, two packages that would nest, and a prefix lifted above one it was under.
- No scanned module lies under an old prefix, whatever its file is called (`text-legacy.py`).

A renamed old contract the parser refuses, such as a `root_layout` child moved one level down, is
no rename either: the comparison stays field by field, where an amendment can accept it.

## Rejected

- Scanning the compared revision: its snapshot holds Python files only, so Dart never matches.
- Renaming every string spelled like a module: it turned `decided_by` and construct values too.
- A rename line that still needs an amendment: the reviewer would redo the check by hand.
- Gained and lost entries with matching tails taken as the rename: that heuristic can hide a
  widening. It stays display only, where no rename holds, for one-to-one pairs of one kind:
  `component 'api'.public gained 'b.api.x' in place of 'a.api.x'` still fails as before.
- A clause on `[scan] namespace`: every new name must lie in the new namespace (exit 2).

## Limits

- Paths are not renamed: a moved `inside` contract stays one finding, since `--against` never
  compares what an inside holds and its path is all that records which inside is trusted.
- Code is judged by name. Two packages trading places read as the rename the contract states,
  a code move between components `--against` never judged. Code copied rather than moved is
  stopped by the clause above only while it keeps an old name: a copy the package rename also
  renamed lies under no old prefix, and only `complete_assignment` or `root_layout` report it.

## Tests

`tests/test_renames.py`; `tests/test_architecture_demo.py` runs `against-package-renamed`,
`against-package-renamed-widened` and `dart-against-package-renamed`.
