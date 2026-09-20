# AD-45 `analyzer` declares a three-part inside, the way `check` already does (AD-20)


`src/archkeel/analyzer/architecture-contract.json` names `orchestration` (`bridge`, `runtime`,
`embedded/scanner.py`, `embedded/report.py`, `embedded/contract.py`), `collectors` (the ten
modules `COLLECTORS-ISOLATED` already names: `bindings`, `calls`, `constructs`, `contexts`,
`dependencies`, `imports`, `references`, `symbols`, `typing_signals`, `violations`) and
`foundation` (`records`, `source`, `resolve`, `receiver_types`, `graph`); the top-level
`analyzer` component points `inside` at it, and `REQUIRES-COMPLETE` is the inside's only rule,
exactly as `check`'s is. Reason: `init --source src/archkeel/analyzer --namespace
archkeel.analyzer` still drafts 3 components one per child path, `bridge`, `embedded` and
`runtime`, with `embedded` alone holding 19 of the scope's 22 modules and 46 of its inner edges
([AD-38](ad-38-a-drafted-component-carries-the-size-structuremetrics.md)); a fresh `archkeel report` on this repository observes 49 module edges with both ends
under `archkeel.analyzer`, and every one of them fits one of three shapes: `scanner` calling
each collector and reading `records`, `source` and `resolve` directly; each collector reading
only `records`, `source`, `resolve`, `receiver_types` or `graph` and never a sibling collector,
which is what `COLLECTORS-ISOLATED` already held; and `report` calling `contract`, `scanner` and,
once, `violations` directly, bypassing `scanner` for that one collector. That last edge is why
`orchestration` requires the whole `collectors` component rather than naming `scanner` as the
only caller: a `through` list naming just the modules `scanner` reaches would have made
`report`'s direct call to `violations` a `complete_requires` violation the layout does not
deserve. Two modules stay owned by neither sub-component: `archkeel.analyzer` (the port's
`observe`) and `archkeel.analyzer.embedded` (an empty `__init__.py`); a `packages` entry is a
dotted prefix ([AD-42](ad-42-a-requires-entry-may-name-the-modules-it-goes-through-and.md)'s `in_scope`), so naming either of these two package roots explicitly would
also claim every module below it, the same reason `check`'s own `archkeel.check` module is the
one [AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md) says no sub-component owns, doubled here because `embedded` nests one directory
deeper than `check`'s flat layout. `archkeel.analyzer`'s public surface, the module
`archkeel.analyzer` itself, is declared under `orchestration` regardless, since
`inside.public_mismatch` compares the two levels' `public` lists as sets, not against
`packages` ownership.
Two cheaper layouts were rejected. One component per direct child directory is what `init`
already drafts and is exactly what this decision replaces, since it hides `embedded`'s size
behind three bare names ([AD-38](ad-38-a-drafted-component-carries-the-size-structuremetrics.md)). One component per collector was rejected because
`COLLECTORS-ISOLATED` already forbids the only edges that would distinguish ten single-module
components from each other; ten components each requiring only `foundation` say nothing that
grouping the ten under one `collectors` component, itself requiring `foundation` once, does not
already say, and it would multiply `REQUIRES-COMPLETE`'s bookkeeping by ten for no discovered
edge. Limit: `oversized_insides` ([AD-33](ad-33-a-components-inside-is-a-level-not-a-list-of-pairs.md)) compares a component's raw module and edge count
against the top level's own, not against whether it has a declared inside, so `analyzer` stays
one of the three `oversized_components` this repository reports before and after this decision,
the same way `check` never left that list once its own inside was declared. Check:
`tests/test_self.py` reads `analyzer`'s inside contract, its modules and its rule the way it
already reads `check`'s; `archkeel validate --root . --json` and `archkeel report --root .`
both pass with zero violations on the current source.

