# Dart input grammar ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Remove the 31 written prefix/suffix control comparisons from the guarded Dart Python implementation while retaining actual Dart behavior and conservative evidence.

**Architecture:** Existing syntax owns the single name-to-Visibility ingress; immutable bindings carry the resulting nominal value. Existing parser owns comment delimiters and formatting lexemes. Snapshot owns filename and pubspec input grammar; resolver uses semantic path APIs, its existing URI/type domains and actual parser CALL/computed facts. No source module, AST framework or coverage authority is added.

**Tech Stack:** Python 3.11, pinned tree-sitter-dart, standard pathlib, existing HRC Target/native observer, remote GitHub and hosted Actions only.

**Spec:** Root-approved four-owner design and compatible public DTO decision, recorded below; existing docs/architecture/dart-nominal-controls.md and dart-python-target.md remain behavioral constraints.

## Global Constraints

- Source inventory base: 0e3b8a7f62b9b13417cda78e11b52d0de82986cd.
- Native prefix observer is the separate f624d99286983fa0e26aff5e87835c359ba63d55 overlay, not an unclaimed existing Dart-project capability.
- 31 new guarded violations: collect 4, parse 15, resolve 10, snapshot 2 (38966921173/job117195558561). No whitelist, guard reduction, raw Final alias, cast/Any/ignore or accepted new debt.
- Public frozen/slotted ResolvedBinding retains its exact seven positional/keyword fields; visibility is init=False and recomputed once at each binding ingress, including dataclasses.replace(name=...).
- Names, paths, IDs and excerpts remain data. Open filename/URI grammar is decoded at its owner; later closed decisions use actual nominal values or existing semantic APIs.
- No new Site receiver-form field: existing computed and exact CALL inventory own that evidence. Do not invent a call solely from closing punctuation.
- Unknown, ambiguous, incomplete, external and malformed inputs stay conservative. No new resolution/analysis authority or forced UNKNOWN-to-PASS change.
- Product branches contain no auxiliary workflow. Root coordinates final independent Astra and integration.

## Review Focus

- Visibility uses the final written qualified-name segment, including Unicode, named/unnamed private constructors and private owner/public member distinctions.
- Old ResolvedBinding seven-field constructors, replace(name=private/public), frozen and slots behavior remain valid.
- Nested comments, comment-looking string contents, raw/triple strings and unclosed block comments preserve source spans and parser concerns.
- Hidden .dart and malformed *.dart names remain selected for the existing validation/problem path; suffix migration must not silently omit them.
- Constructed receivers must have real bounded parser CALL evidence; computed/index, missing/ambiguous calls, closures and incomplete syntax cannot acquire invented targets.

## Owner ports and consumers

1. syntax.py: Visibility.from_name(spelling: str) -> Visibility, backed by the one private name-start token domain. Parser declaration/member producers, synthetic enum/import/binding Fact producers and ResolvedBinding ingress use this decoder. Resolver construction privacy and accessibility consumers read ResolvedBinding.visibility.
2. resolve.py: ResolvedBinding.visibility: Visibility = field(init=False), set only in __post_init__; existing 9 construction sites retain their seven arguments. Existing _TypeToken handles final generic punctuation. Path.is_absolute/is_relative_to replace prefix safety checks. UriScheme remains at the actual resolver owner: snapshot has no URI consumer.
3. parse.py: private _CommentDelimiter and _comment_delimiter(data: bytes, index: int) -> _CommentDelimiter | None are consumed by the existing unclosed-comment and trivia loops; existing _Lexeme handles parameter delimiters, nullable marker and canonical comma/dot punctuation. Actual CONST node kinds classify constructors. Existing CALL/computed facts are sufficient for resolver receivers.
4. snapshot.py: private nominal source suffix decoder consumes filenames (including .dart); the existing pubspec parser owns complete empty/comment-line grammar. Canonical ResolutionRole and RuntimeRequirementState remain shared unchanged.

No import edge is added: parse -> syntax, resolve -> syntax + snapshot, collect -> all three already exist. No new public module or second vocabulary inventory is introduced. Expected production cost before real measurement: approximately 80-130 net lines, mainly explicit typed ingress; exact diff and runtime cost must be reported.

## Task 1: Native RED and preserved behavior

- [x] Commit this plan and actual behavior/API probes before product code.
- [x] Run the unchanged native Dart guard against the real f624 observer overlay; print trace-valid rows with exact source spans, rules and construct IDs.
- [x] Observe actual missing Visibility ingress/field failures and constructor const-prefix false-positive; retain passing comment/string controls.
- [x] Inventory actual tracked ResolvedBinding/Site construction and documented API usage with git grep, not assumptions.

## Task 2: Minimal owned grammar and authored ports

- [x] Publish new Visibility ingress/derived binding field in the existing Dart Target before implementing them; actual source-widening mutations must fail under unchanged authored intent.
- [x] Implement the four owner changes without extra state, reader-side private-name parsing, duplicate enum/string inventories or an AST framework.
- [x] Run new and existing Dart parser/resolver/directive/snapshot/SDK-free/partial-UML/false-positive/differential controls, Ruff, formatter and strict mypy.
- [x] Prove all five existing whole-module Python guards pass under the real prefix observer and injected raw literal/Final/prefix/suffix controls remain trace-valid FAIL.

## Task 3: Freeze and independent review

- [x] Compare complete actual Compass syntax/Facts/targets and relevant UNKNOWN semantics to the exact predecessor; explain any genuine corrections.
- [ ] Run Compass complete reports/browser acceptance, existing project suite and normal baseline/amendment/no-write with no increased budget.
- [x] Record exact product/Target/test costs and parser/resolver runtime; freeze clean source without workflows.
- [ ] Hand source and genuine RED/GREEN evidence to Root for independent final Astra; create a Part of #542 PR only after approval, no self-merge.

## Decisions

Root explicitly approved inline plan/RED then implementation of these four existing owners. Public ResolvedBinding is exported by DART-RESOLUTION and authored with all seven fields in the Target, so a required eighth constructor argument was rejected. The compatible derived field performs one centralized decode per binding ingress; later resolver checks consume the typed value.
Root approved removal of the redundant receiver.endswith precheck in favor of the existing exact parser CALL inventory, and existing computed for index receivers; no additional Site API/state.

## Execution ledger

Actual RED 38973308034/job117216624183: 11 expected failures and 6 controls passed against unchanged Dart source. Missing owned Visibility ingress/field and the real lowercase constance() false-positive are reproduced. An initial probe used the wrong parser signature; that probe was corrected before this authoritative RED and no product code was written in between. Native job117216623885 reports the same 31 trace-valid existing prefix/suffix violations under the explicit f624 observer overlay. Actual tracked constructor inventory shows nine existing resolver producers and no earlier direct test constructor uses; HRC nevertheless explicitly exports the seven-field DTO, so compatibility is retained.

Native comparison 38975669351/job117224390415 runs the same frozen f624 observer on real clean revisions 0e3 and 47633: all 31 Dart predicate violations disappear, all five existing Dart guards are evaluation-proven PASS, unresolved calls 865 -> 840, typing 52 -> 52, selected UNKNOWNs 58 -> 58. Complete kind/subjects/rule_ids/data projections agree for all 30 positions, 20 routes and 8 UML unknowns. The 20 remaining violations belong to the independently owned TypeScript input migration; no global PASS is claimed.

Complete canonical Fact wire already agrees under the same runtime for H-uml-dart (226636 bytes) and Compass (10669901 bytes). The initial stronger whole-Syntax comparison exposed constructor visibility fields where the old parser disagreed with the already-existing collector wire. Final verification must prove each actual constructor/name/span and old wire metadata rather than whitelist a count.

The new receiver controls separately exposed the pre-existing local function shadowing defect #570. Identical unchanged-source tests on real 0e3 and 1f have exactly the same two failures and one passing index control (38976296732). Shadowing assertions and its future fix move to an independent issue/branch; this migration retains the index and missing-real-CALL controls and does not accept the false resolution.

Final constructor-form differential38977153051/job117229248555 is GREEN: both complete H/Compass Fact byte streams agree without projection. Every actual changed Member.visibility is a constructor with unchanged name/owner/span, agrees with the previous collector's constructor/factory visibility, and is tied to that previous record's actual matching source citation. All other Syntax fields agree. This found 25 such constructors across the actual fixture; the test does not whitelist this count or any filenames.

Current focused controls84PASS; actual Compass reports including Chromium generated-detail navigation4PASS (38977153051/jobs117229248696/117229248430). Ruff passed; a test-only string concatenation formatting difference is corrected. Whole-source quality/native integration remain pending after the source cost check.

Three alternating full collection samples measured H0.08574s ->0.09103s (+6.17%) and Compass6.78348s ->7.43895s (+9.66%). This is a regression, not an improvement claim. Root approved actual profiling first; only if the removed punctuation precheck caused repeated file-wide CALL scans may a resolver-local index of those same real facts replace the scan without any new DTO, inference, semantics or authority. #570 remains independent.

Actual cProfile38977608002/job117230695674 identifies repeated PurePosixPath allocation as the main regression: 57365 resolve_uri calls take1.87s before vs3.42s after under profiling; current _source_at has41975 calls and1.15s cumulative cost. Parser11.75s vs11.82s is nearly unchanged. Root approved a small instance-local cache of actual PurePosixPath values in the existing Resolver; lifetime follows one immutable source snapshot, path spellings remain open data, no resolved targets are cached and no receiver index is added. _module_path becomes a private Resolver method so it consumes that same cached ingress instead of allocating a second path representation.

## Final frozen source and evidence

Source/Target/tests are frozen at f31b4c1bdabbf81ec47aed71ac0f91cdb869909d, against 0e3b8a7f62b9b13417cda78e11b52d0de82986cd. Final run38978028432 has all five jobs GREEN:84 focused controls and actual Source mutations, Ruff,9 formats, strict mypy139;317 existing Dart tests;4 actual Compass reports including Chromium detail navigation; complete H226636B/Compass10669901B Fact wire and all per-constructor syntax/citation proofs; native real-source metrics and five guards. The focused selection excludes the unrelated global self-run fixture while the independent TypeScript20 predicates are not yet migrated. That fixture is not weakened, skipped in product tests or claimed green; Root owns the combined activation.

Native frozen observer f624 runs on the actual clean revisions:51 ->20 violations (all31 Dart predicate violations removed, TypeScript20 remain),865 ->840 unresolved calls,52 ->52 typing,58 ->58 UNKNOWN,18692 ->18691 total calls. All five existing Dart whole-module rules are evaluation-proven PASS. Complete 30-position/20-route/8-UML kind/subjects/rule_ids/data projections agree, excluding IDs/citations. Artifact12079169365 contains both full observations. No whole-run PASS, per-call/PARTIAL identity equality or increased analysis capability is claimed.

Exact production cost is +69 net lines across five existing owner files; authored Target +56, tests +228 net, spec +24, plan documentation additional. No source module or dependency is added. The private path cache is seven net lines beyond the earlier migration, does not cache resolutions, and has exactly one Resolver/snapshot lifetime.

Final concrete cost run38978331605/job117233017290 loads all six actual Dart modules from original0e3, uncached252040 and cachedf31 into a common runtime on one runner. All three complete Compass10669901B Fact streams agree. Six balanced alternating samples give medians original6.81015s, uncached7.48177s, cached7.15162s: cache -4.41% against the exact uncached change, final still +5.01% against the original. This bounds a real regression and does not claim a speedup. The separate five-pair H measurement was +4.21%,1.83ms. No further performance infrastructure is proposed.

Root received the clean source snapshot for the combined TypeScript input/prefix observer/Dart activation. Independent Astra review is queued; normal committed baseline amendment/receipt/no-write and final Main restack remain pending on that combined source. No baseline budget is changed in this branch. #570 remains the separate DraftPR572 with independent approval and its own source delta.
