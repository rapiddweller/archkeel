# Execution ledger — typed component contracts

User authorization: implement separate changes, use Superpowers, obtain independent final Astra reviews and merge after green checks. The later clarification includes parser and protocol values. Issue #542 remains open until that expanded scope is complete.

## Ownership

- Pure ir.dependency owns dependency selection. One model adapter preserves legacy ownership order and duplicates. Core and reports consume the same prepared selection.
- Shared facts own Language, source-profile identifiers, source-section names and runtime-requirement state. Input codecs convert once; consumers use the same types.
- Graph owns graph and assessment vocabulary. The Core RuleVerdict compatibility export names the shared assessment type; declaration status remains a separate domain.
- Language parser modules own external syntax conversion. Closed semantic DTO fields have nominal types; unknown syntax remains unknown. JSON keys, module names, supplied paths and user identities remain open string data.
- CLI owns argparse decoding and installation choices. Core never imports CLI.
- No generic global vocabulary, copied historical observation Target, second API inventory, increased debt ceiling or parser exemption is authorized.

## Reviewed PR frontier

| PR | Current head | Evidence and state |
| --- | --- | --- |
| #543 / #540 | 08b6e005479a0dc53cc85a71274530046bb02926 | Independent Astra approved original and test-only follow-up. Required CI 38935150643 green. |
| #545 / #541 | 2299b77cf7d07d44143aab54b32d3cbf3a3c60c5 | Independent Astra approved production. Only the same three approved suite-fix files follow that review. Required CI 38935388253 green. |
| #546 / first #542 increment | a9f09f8bd8afbeb4d6c192cd868387768a6720a4 | Independent Astra approved production and holistic first-three review. Required CI 38935423489 green. Does not close expanded #542. |
| #547 / state protocol | 3a0c654368a93d53fe18454c9fac6d25ed3a639a | Independent Astra approved production. Required CI 38935512164 green. Native 65 unknown / 919 unresolved / zero violations. |
| #548 / comparison observer | 61404f1cf9e8579929119be093c3676075754661 | Literal-left extension: expected RED then 496 tests/native green in 38936967356. Final Astra identified inherited value and custom Enum construction risks; conservative repair and real counterexamples are in progress. Not approved for merge. |

The three suite fixes are an exact export-plus-identity expectation, inclusion of that compatibility test in required Core checks, and a Playwright locator wait that preserves CSP and the original attached-element predicate. GitHub comparisons confirm these are the only changes after the earlier approved heads.

## Full regression

Initial run 38928014179 completed with 9,234 passed, 18 skipped and three failures: the stale new-export expectation, the CSP-blocked test wait, and a stray auxiliary workflow formatting file. Product fixes are in #543 and carried through the stack. The verification workflow now checks committed formatting and uses RUNNER_TEMP.

Corrected full run 38937362895 checks product head 95f514d362eef18cdd07fec50de1b7f46e94545c with only its auxiliary verification workflow added. Its native job is green; the complete browser/source suite is running. Later feature increments need their own final regression evidence.

## Expanded migration work

- #544 exact caller-scoped module-object grants: original native/lifecycle and schema regressions green; integration against #548 and fresh amendment are in progress. No broad module or symbol publication.
- TypeScript configuration/resolution: stable carrier b82eb4419209ad9df2220c4a248938e70737e2c1; 429 tests and 28 compiler/differential tests green. Native unresolved calls improve 919 to 918 and baseline tightens. A small JSON-field presence API is being checked against the stronger observer; closed modes remain enums.
- Collector protocol/facts: canonical owned types, strict tag decoding and necessary consumers are under final native integration. A prior protocol-version Target mismatch is repaired; no final global pass is claimed yet.
- CLI: clean seven-file carrier 0ba1c254bc596fe4ecb3bf2219d5c9dc1d328156. 154 compatibility tests, exact help bytes, static checks and all 56 CLI Target assessments pass. Final whole-repository gate awaits the shared protocol predecessor.
- Graph: owned types and historical schemas pass; remaining consumer and unresolved-call integration is not complete.
- TypeScript syntax, Dart syntax/resolution/snapshot, Python control categories, remaining contract grammar and presentation/browser protocol remain pending. Each needs an explicit owner, native RED/GREEN and review before being marked protected.

## Merge gates

Keep #542 open while any expanded migration remains pending. Resolve Important review findings. Merge reviewed PRs in dependency order only after the applicable exact-head CI and corrected full regression are green. Preserve actual ancestry, policy/baseline amendment digests and earlier feature deltas when updating stacked bases. Verify issue closure after merges.
