# AD-105 A package rename is compared under its new names

`validate --against <ref>` reported package renames as widenings and omitted replaced public entries (#151, AD-61).

Moved component packages propose a prefix substitution: `shop.render -> shop.view`,
or `window_cleaning_mobile -> field_service_mobile` with `...features.kunde -> ...customer`.
Pairs drop unchanged trailing segments. Packages pair by a last segment unique on each side,
or as the single remaining pair. A proven substitution renames the old contract and baseline
before `ir.widening` compares them. JSON `renames` (`null` without revision comparison) and the
terminal name the substitution. Unexplained changes still compare; a real widening still fails.

| Historical `validate --against` comparison, same input | `main` | After this change |
|---|---:|---:|
| shop sample: `shop.render` moved to `shop.view`, its import and the contract | 12 failures | 0 |
| the same, and one gained `allowed_sources` entry | 13 | 1: that entry |
| G-dart: package `shop -> field_shop`, `lib/presentation -> lib/ui` | 21 | 0 |
| shop sample: `shop -> store_app`, scan roots and namespace included | 85 | 1: moved `inside` |
| Archkeel itself: `archkeel.host -> archkeel.hosting`, with its baseline | 5 | 0 |

Rename only module and symbol fields listed by `ir.model.module_references`, never ids, labels,
kinds, `decided_by` or constructs. Renaming root `agent` to `architect` still reports changed
`decided_by` values. A test classifies every contract string as a module field or a non-module.
Baseline subjects, roles and accepted names are renamed, except component-cycle labels.
`reference.namespace` still checks entries marked `held`; commands, path steps and shims are
renamed but not held.

## When a substitution holds

- Preserve every prefix relation among contract names, baseline names and renamed prefixes.
  New names must retain the same containment and rule, package and entry scope. Reject merged
  or nested names, an existing `shop.view` grant passing to renamed code, a `shop` rule losing
  coverage, an `other` rule gaining it, or a prefix lifted above its former ancestor.
- No module the scan reads or an import reaches lies under an old prefix, whatever its file is
  called: an imported `shop/render/legacy.pyc` left behind stops it.
- The scan layout must place each old prefix. `shop.view.text` in `shop/view/text.py` uses the
  root; Dart `field_shop.ui` in `lib/ui` gets `field_shop` from `lib`. A renamed base maps old
  names there too. Reject unmappable prefixes or any remaining file there or beside it as
  `render.*`, scanned or not: copies, newly named files and files outside narrowed roots count.
  `__pycache__` is not code; Python reads it only beside source. The CLI reads historical
  `--config`; missing or invalid config or omitted `against_config` for direct callers cannot
  authorize a rename. Every Python candidate needs a complete historical scan under that
  config: physical layout can change without changing roots or namespace strings. Dart
  supports only its existing same-root path; changed-root renames remain unsupported.

Candidates go shortest first; unparseable renamed contracts are skipped, then compared field by field.

Approved on 2026-09-26 (#158): publish the existing `check.snapshot.resolve_commit` in `check`
and nested `foundation`. The CLI already uses it; its coupling ceiling and baseline move 9→10.

## Rejected

- Using the Python-only revision snapshot to prove a Dart layout: it contains no Dart sources.
  Python renames do require the historical scan described above.
- Renaming every string spelled like a module: it turned `decided_by` and construct values too.
- Requiring an amendment for a proven rename outsources the check; matching name tails stays
  display-only (`gained 'b.api.x' in place of 'a.api.x'`) because inferring a move can hide widening.

## Limits

- A moved `inside` path stays one finding: `--against` never compares what an inside holds.
- Code is judged by name and place: two packages trading places read as the rename the contract
  states, a code move between components `--against` never judged.

Tests: `tests/test_renames.py`, `tests/test_rename_physical_roots.py`, and rename demo rows.
