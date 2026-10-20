# Run 1: independent review of `fixtures/M-review-workflow` (16d3e6b)

| Identity | Value |
|---|---|
| Fixture commit | 16d3e6b (oracle `expected-findings.md` committed in the same commit, before the run) |
| Skill | CLI-installed `.claude/skills/archkeel/SKILL.md`, sha256 `85623ccf…`, identical to `skills/archkeel/SKILL.md` |
| CLI | `archkeel 4.0.2.dev63+g81ce75ace` |
| Reviewer | fresh subagent (Sonnet); saw only the isolated fixture copy and the installed skill, not the oracle |
| Request | "complete architecture review using the physical structure review from the skill" |

## Grading against the committed oracle

| Item | Oracle | Run | Result |
|---|---|---|---|
| Trace, coverage, finding format, tool vs. judgment | required | all present; 100 % package coverage; tool facts (12/12 PASS, projection UNKNOWN, agent-decided) kept apart | match |
| S1 generic leaf `common.util` | simplify | simplify: delete unused `chunked`/`now_iso`, move `slugify` to its only caller | match |
| S2 public `round_cents` | simplify | simplify: one checkout operation for the total; drop entry→pricing/rounding; remove from public. Also found `quote` skips the quantity guard | match |
| S3 discovery `load_backend` | keep | simplify: lazy importlib not justified because `sqlite3` is stdlib; `.BACKEND` from `ModuleType` hides `Any` | mismatch, fixture defect |
| S4 `pricing` (10 modules) | keep | simplify: eight classes differing only by a multiplier → one rate table | mismatch, fixture defect |

Both mismatches are fixture defects, not skill defects: the fixture gave no reason for lazy
loading and no region-specific logic, so the reviewer's simplification is the correct
judgment. The oracle is not changed after the fact; the fixture is.

## Further findings that are real fixture defects

- `sqlite` backend wrote to a fresh `:memory:` database per call and persisted nothing.
- `Receipt.quantity` was dropped by `save(sku, total_cents)`.
- Nested contracts reused the root rule rationales ("entry, checkout, pricing and storage"
  inside checkout); checkout's three one-module children were over-granular.
- `docs/target.md` named one entry point; the contract declares two.

## Skill gap shown by this run

The reviewer could not name the symbols behind `unreferenced_symbols: 19`. They are listed
only on the `report --only architecture` page ("Review claim: symbols nobody references");
the skill said only that the commands "report claims". The skill now says where the names are.

## Navigation smoke test (acceptance 4)

The reviewer served `test-artifacts/` over HTTP (the browser pane refuses `file://`) and
opened nested scopes (`checkout`, `storage`, `checkout:checkout-service`,
`storage:storage-backends`), the module detail page and its back link: no broken
navigation. Side note: at `storage:storage-backends` the breadcrumb shows
`orders / storage` without the sub-component. A stray `architecture.json` without its detail
companion came from a mistyped first run, not from the tool.
