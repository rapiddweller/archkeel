# Report reuse and PR separation

DRY/SPOT decisions take priority. Source-spelling privacy and cross-package symbol
classification have canonical owners; violation and UNKNOWN consumers use the same
effective dependency profile. These are bounded consolidations, not proof that the
repository contains no other duplicated decisions.

One report invocation derives immutable module exploration once and shares it
between its two HTML pages. Matching Core projection validation still precedes
this work. Standalone APIs remain compatible; later report invocations recompute.

The earlier combined branch (`a6d11d39`) measured 82.484 to 80.755 seconds on one
frozen 1,174-file / 37-contract EE CLI pair (2.10%). Both HTML files were byte-identical.
That measurement predates the PR separation; the exact smaller head has not been
remeasured. The initial 27.33% full-CLI checkpoint has its own separate receipt in
[collector-performance-2026-10-19.md](collector-performance-2026-10-19.md).
No memory saving or stable tail-latency improvement is established.

A broad facade memo was measured and removed: 1.307 Core CPU seconds did not justify
its plumbing and more than 313,000 negative entries. It is absent from both PRs.

On 20 October, CI run 39367566451 confirmed the combined branch's known failures:
145 SOURCE-MAX500 violations, 854 unresolved calls against 838, and two file-inventory
gaps. Report tests rejected the same rule through the shared self-report fixture.
The amendment was valid; no workflow defect caused these failures.

The user authorized separate PRs. Performance/DRY remains in #621. Native file rules,
DTOs, snapshot integration, schema, rule tests and responsibility-based file moves
remain together in `feat/contract-source-maintenance`. The hard target and findings
are preserved; no violation allowance, budget increase or test bypass was added.

LOCAL VERIFIED: all 126 native rule assessments pass, with zero violations and
UNKNOWN positions. Calls are 827; the baseline was tightened accordingly. Focused
Core checks: 417 PASS. Report suite: 84 PASS. Lint, typing, build, wheel/sdist smoke,
browser build checks and Mermaid pass. Astra found no material split findings.
The broad Core run was interrupted with 6150 visible passes, 13 skips and seven
failures; it has no complete summary and is not a passing result. A retry with
verbose node IDs and immediate failure reporting is investigating the first error.

CI-ONLY VERIFICATION: the old combined head failed; the smaller head is submitted
for fresh CI. Merge is conditional on successful checks.
