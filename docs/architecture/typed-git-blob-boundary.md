# Typed regular Git blob boundary

Base: `bb3e498b9c43afc954ef9fe7078595983e0b3c2f`.
The source-only carrier is `bf21e014fff57e5b963ea6785ae4a4b4f2c48a79`.
Production changes two existing files, net +16 lines.

Both readers previously repeated the mode/type decision. The existing snapshot
owner now recognizes the two supported regular-file pairs once and returns
`RegularGitBlobKind | None`. Git already depended on snapshot. No new module,
DTO, generic converter or global Git vocabulary was introduced. Paths, revisions,
object IDs, payload bytes, path selection and reader-owned errors retain their
existing contracts.

The independent authored Target protects the enum owner and both byte inputs plus
the nominal optional return. Three function-scoped native guards protect the
ingress and its two consumers. The enum placement policy authorizes only the
snapshot domain owner. A consumer copy of the actual enum still yields a
trace-valid placement violation while the canonical API remains present.
Tuple-valued enum members are runtime-tested; no static member-value proof or
whole-module absence of string comparisons is claimed.

## Verification

- [Native RED](https://github.com/rapiddweller/archkeel/actions/runs/39001416619/job/117304955181):
  two actual byte-dispatch controls fail their native guards; two API/Target tests
  fail before production exists, without import failures.
- [Final scoped tests](https://github.com/rapiddweller/archkeel/actions/runs/39001939211/job/117306525479):
  27 pass, including input/return widening, three raw byte-dispatch mutations,
  exact accepted/rejected pairs and narrow enum placement.
- [Existing regressions](https://github.com/rapiddweller/archkeel/actions/runs/39001939211):
  76 Git/snapshot/language tests pass; committed Ruff formatting and strict MyPy
  for 150 source files pass, as do 11 repository hygiene tests.
- [Actual two-version wire replay](https://github.com/rapiddweller/archkeel/actions/runs/39001658088/job/117305678501):
  isolated, path/hash-verified old and new modules return identical complete
  payload/archive bytes and error types/text for regular/executable blobs,
  symlinks, Gitlinks, missing paths and four malformed metadata inputs.
- [Final site proof](https://github.com/rapiddweller/archkeel/actions/runs/39001939211/job/117306525371):
  same current observer on the actual before/after trees; unresolved calls remain
  836 and partially resolved calls remain 2508. The signed AST/status/reason/
  targets/candidate-count multisets retain multiplicity and have no positive or
  negative payload deltas. No type-position or target changes are observed.
  This proof does not compare every resolved call or all outer evidence fields.

The UNKNOWN comparison selects record ID, kind, subjects, rule IDs and complete
data. Its 61 selected records are unchanged: 30 boundary positions, 20 routes,
three boundary limits and eight UML conformance records. The separately measured
`unknown_positions` scalar remains 58. These are distinct counts.

[The normal writer](https://github.com/rapiddweller/archkeel/actions/runs/39002101657/job/117307013702)
produces the canonical amendment and baseline. Its only baseline change is
838 to 836 unresolved calls, an inherited improvement already present at the
pinned base, not a benefit claimed for this Git change. No allowance or other
budget changes. The writer reports zero violations, 52 typing positions and
58 unknown positions.

[Committed NoWrite](https://github.com/rapiddweller/archkeel/actions/runs/39002515729/job/117308244483)
checks exact tested source/intent blobs, canonical receipt bytes, the inherited-only
baseline difference, scoped native tests and strict quality. Validation exits zero
with empty failures/diagnostics, a valid committed amendment and a clean worktree.
The combined Root baseline, full-suite gates, final independent Astra review and
merge are separate integration responsibilities.
