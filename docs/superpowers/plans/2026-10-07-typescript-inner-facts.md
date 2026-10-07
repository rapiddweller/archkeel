# TypeScript inner facts implementation plan

> Execute with Luna implementers; primary reviews and integrates.

**Goal:** Complete #348 inside PR #386.
**Spec:** https://github.com/rapiddweller/archkeel/issues/348
**Architecture:** Tree-sitter stays inside `typescript.parse`. The collector emits source facts through the existing process port. Core validates capabilities and builds the existing UML graph; Target and rendering remain outside the collector.
**Stack:** Python, existing tree-sitter grammar, pytest, existing browser acceptance.

## Constraints

- Keep old import-only payloads readable and UNKNOWN for unmeasured sections.
- No compiler, Node runtime, new dependency or second graph model.
- No Python-only proof enabled by publishing TypeScript symbols.
- Preserve the 576-case import differential and assertions. Alex accepted the remaining
  self-call budget of 715 on 2026-10-07 after a bounded sample; other budgets stay unchanged.
- Module inventory remains partial unless explicitly certified; class member receipts prove only their named lexical kinds.

## Tasks

- [x] Frontend: extend `typescript/parse.py` and `collect.py`; test source definitions, signatures, visibility, static members, bindings and typed relationship sites in `tests/test_typescript_inner.py`.
- [x] Core: accept exactly the registered six-section `inner-uml-v1` capability, retain legacy null sections, validate receipts and reuse `source_graph.py`. Test compatibility, forged capabilities and UNKNOWN absence.
- [x] Demo: extend independent `H-uml-typescript` intent and `demo_catalog_uml.py` with matching, mismatch and partial cases. Check real dark-mode browser output, shared navigation and unchanged report data.
- [ ] Primary: review soundness, update architecture/docs/release notes, measure self-baseline and regenerate self-observation after the last source/config edit. Run focused gates, full local gate, push and verify final CI before merge.

## Review focus

- Parameters, local variables or assignments shadowing a known/imported callable.
- Overloads and merged declarations retaining all candidates rather than one invented target.
- Computed, external or unsupported syntax retaining typed UNKNOWN sites.
- Missing members failing only with complete receipts for the exact owner/kind.
- Legacy import-only observations retaining unavailable inner evidence.

## Integration contract

Profile identity stays `archkeel-typescript-imports`. New payloads declare `inner-uml-v1` and sections `imports`, `unknowns`, `symbols`, `calls`, `references`, `bindings`. Reuse existing symbol records, `member_inventories`, `base_declarations`, `construction` and `result_bindings`; source locations and stable definition identities remain mandatory.
