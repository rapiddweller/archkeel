# AD-311 Studio separates call resolution and claim status

**Decision.** A measured call with unresolved candidates is `partial`. A resolved call is `proven`.
The call graph shows each status as an observed code fact and counts call sites, not edges.

`declared` stays separate as a decision from the architecture target. `unknown` means available
evidence does not resolve the target. It does not prove that no target exists.

`CheckStatus.Claim` keeps the status `claim`. The UI does not assign its source. A story can set
`claim: true`, and a measured partial call can also produce that status. `StoryStep.seam` is
calculated separately and can exist with either source. The current API does not return the input
`claim` flag, so the status and seam do not always identify the source. The legend says
`author assertion or partly resolved call`.

The evidence legend calls `Claim` an authored assertion. Chat identifies agent answers as claims.
The story author can be an agent or a person. No API or schema changes in this decision.

**Reason.** `Proof.Claim` called a measured partial call an agent claim. This joined call resolution
and assertion source. A separate `partial` mark fixes that error for graph views.

**Rejected.** Do not infer that a `partial_call` seam came from the analyzer alone. An author claim
can have the same seam. Do not change the API status without a versioned migration.

**Limit.** Graph views separate `partial` calls from claims. Checked stories still cannot always
separate an author claim from a measured partial call. Issue #872 remains open for that provenance.
The graph API reports outside-scan counts but does not identify each external target. The UI does
not infer external or unloaded targets from missing edges.

**Check.** Browser tests cover call counts, detail labels, the agent chat claim, checked story
statuses, declared-route target colors and grouped views.
`make browser-runtime-generate` type-checks and rebuilds the bundle.
`make browser-architecture-check` checks UI boundaries.
