# AD-105 A package rename is compared under its new names

`validate --against <ref>` compares the contract at `ref` with the one validated field by field
(AD-61). A rename changes every field that names the package, so a rename that widens nothing
read as dozens of widenings, and a `public` entry it replaced was not even listed as lost (#151).

Now the component packages that moved propose a prefix substitution: `shop.render -> shop.view`,
or `window_cleaning_mobile -> field_service_mobile` with `...features.kunde -> ...customer`. A
pair drops the trailing segments the move kept; moved packages pair by a last segment unique on
each side, or as the single one left. When a substitution holds, the old contract and baseline
are renamed with it before `ir.widening` compares them; `renames` in the JSON result (`null`
when no revision was compared) and the terminal name it. Whatever it does not explain is still
compared, so a real widening beside a rename fails alone.

| `validate --against`, same input on `main` and now | `main` | Now |
|---|---:|---:|
| shop sample: `shop.render` moved to `shop.view`, its import and the contract | 12 failures | 0 |
| the same, and one gained `allowed_sources` entry | 13 | 1: that entry |
| G-dart: package `shop -> field_shop`, `lib/presentation -> lib/ui` | 21 | 0 |
| shop sample: `shop -> store_app`, scan roots and namespace included | 85 | 1: moved `inside` |
| Archkeel itself: `archkeel.host -> archkeel.hosting`, with its baseline | 5 | 0 |

## What is renamed

Only the module and symbol fields `ir.model.module_references` lists: never an id, label, kind,
`decided_by` or construct, so root `agent` renamed `architect` still reports each flipped
`decided_by`. A test walks every string of a contract with every field filled and requires each
to be listed or named as no module. A baseline's subjects, roles and accepted names are renamed,
except a component cycle's labels. `reference.namespace` checks the entries marked `held`,
exactly the fields it checked before; commands, path steps and shims are renamed, not held.

## When a substitution holds

Each clause has a test that fails without it:

- Every prefix relation among the old contract's and baseline's names and the renamed prefixes
  survives: one held another before exactly when their new names hold each other. Rules,
  packages and entries scope by prefix, so the renamed contract states for each new name what
  the old stated for its old one. This rejects merged or nested names, a grant given to
  `shop.view` passing to the renamed code, a rule on `shop` that stops or `other` that starts
  covering it, and a prefix lifted above one it was under.
- No module the scan reads or an import reaches lies under an old prefix, whatever its file is
  called: an imported `shop/render/legacy.pyc` left behind stops it.
- The scan's layout places each old prefix: `shop.view.text` in `shop/view/text.py` reads names
  from the root, a Dart `field_shop.ui` in `lib/ui` reads `field_shop` from `lib`, and a base the
  rename renamed reads its old names there too. A prefix it cannot place is no rename, and so is
  one with any file there, or beside it as `render.*`, scanned or not: a copy, a file the package
  rename names anew, or one outside narrowed roots. `__pycache__` is no code; Python reads it only
  beside a source. The CLI reads the selected historical `--config`; missing or invalid config, or
  omitted `against_config` for direct callers, cannot authorize a rename. Every Python rename
  candidate requires a complete historical scan under that config: physical layout can change
  even when configured roots and namespace strings do not. Dart keeps the existing same-layout
  path; changed-root or changed-namespace Dart renames remain unsupported.

Candidates go shortest first; unparseable renamed contracts are skipped, then compared field by field.

## Rejected

- Scanning the compared revision: its snapshot holds Python files only, so Dart never matches.
- Renaming every string spelled like a module: it turned `decided_by` and construct values too.
- Requiring an amendment for a proven rename outsources the check; matching name tails stays
  display-only (`gained 'b.api.x' in place of 'a.api.x'`) because inferring a move can hide widening.

## Limits

- A moved `inside` path stays one finding: `--against` never compares what an inside holds.
- Code is judged by name and place: two packages trading places read as the rename the contract
  states, a code move between components `--against` never judged.

## Tests

`tests/test_renames.py`, `tests/test_rename_physical_roots.py`, and rename demo rows.
