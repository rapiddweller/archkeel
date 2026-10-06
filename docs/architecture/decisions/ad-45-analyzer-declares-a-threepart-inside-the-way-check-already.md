# AD-45 `analyzer` declares a three-part inside, the way `check` already does (AD-20)

The analyzer inside contract declares:

- `orchestration`: `bridge`, `runtime`, `embedded/scanner.py`, `embedded/report.py`,
  `embedded/contract.py`.
- `collectors`: `bindings`, `calls`, `constructs`, `contexts`, `dependencies`,
  `imports`, `references`, `symbols`, `typing_signals`, `violations`.
- `foundation`: `records`, `source`, `resolve`, `receiver_types`, `graph`.

The parent points `inside` to `src/archkeel/analyzer/architecture-contract.json`;
its only rule is `REQUIRES-COMPLETE`, as in `check`.

Directory-based `init` hid 19 of 22 modules and 46 inner edges in `embedded`
([AD-38](ad-38-a-drafted-component-carries-the-size-structuremetrics.md)). All 49
analyzer edges fit orchestration calling collectors/foundations, collectors reading
foundations without peer imports, and `report` calling `contract`, `scanner` and
`violations`. That direct `violations` call requires the whole collectors component;
a narrower scanner-only `through` permission would reject legitimate flow.

`archkeel.analyzer` and empty `archkeel.analyzer.embedded` remain unowned inside:
package-prefix ownership would also claim every child
([AD-42](ad-42-a-requires-entry-may-name-the-modules-it-goes-through-and.md),
[AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)). The original
matching-public check nevertheless placed `archkeel.analyzer` under orchestration.

Ten collector components would duplicate `COLLECTORS-ISOLATED` and ten identical
foundation requirements. Raw size claims ignore declared insides, so analyzer
remains oversized ([AD-33](ad-33-a-components-inside-is-a-level-not-a-list-of-pairs.md)).
Original checks: `tests/test_self.py` inspects the inside; self `validate --json`
and `report` passed with zero violations.
