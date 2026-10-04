# Report review pilot

Status: tasks and fixtures prepared; no human results yet. Refs #236.

Hypothesis: starting with findings and source evidence helps reviewers decide correctly
and find the source faster. Browser tests establish working controls, not that hypothesis.
Keep the existing offline explorer until observed task failures justify another application.

## Prepare the reports

Use the catalog cases below in clean checkouts of the control and candidate revisions.
Record both full commit IDs. Generate each into a new destination:

```bash
make demo-architecture VARIANT=class-a-forbidden-dependency-pair OUTPUT=review-output/dependency.json
make demo-architecture VARIANT=class-a-boundary-types-mixed-evidence OUTPUT=review-output/mixed.json
make demo-architecture VARIANT=class-a-boundary-types-ordinary-reexport-chain-unknown OUTPUT=review-output/unknown.json
make demo-architecture VARIANT=class-a-recursive-wide-package OUTPUT=review-output/wide.json
make demo OUTPUT=review-output/checks
```

Some catalog replays exit `2` because validation rejects the fixture. They still produce
valid reports; inspect the report's own verdicts. `make demo` verifies the expected check exits.

For a scored pair, both layouts must use the same saved result and canonical observation.
Use `render_architecture_html(result, architecture_json, ...)` for snapshot reports and
`render_check_html(result, ...)` for Check A. Both require a typed `RunResult`.
Freeze the source/contract digests, findings, UNKNOWNs, assessments and measurements.
Keep renderer revision and observer provenance separate. Reject a pair if its evidence differs.
Use `clean` for an unscored introduction; participants must not see the answer key.

## Tasks and facilitator answer key

| Case | Ask the reviewer | Required answer |
|---|---|---|
| Dependency | Find the forbidden crossing and its source. What should change? | `shop.render` imports `OrderRepository` from `shop.store`; `DEP-RENDER-NO-STORE` forbids it. Fix the crossing or request an explicit target decision. |
| Mixed evidence | Did `APP-TYPES-NOT-DICT` pass? Explain with source evidence. | `FAIL`: `snapshot(context: dict, future: FutureOrder)` has a confirmed dict violation and an unresolved type. The UNKNOWN filter keeps the FAIL assessment with its violation and undecided counts. |
| Unknown facade | Does no confirmed violation certify the render interface? | `UNKNOWN`: an ordinary re-export hop lacks literal `__all__`; the signature route is unproven. |
| Wide package | Find `shop.store.backend.tasks.isolated`. What does an absent visible edge establish? | Locate the module in Actual/Structure. The displayed static graph does not certify runtime behavior. |
| Check A | Why reject a candidate with no new violations? Does Actual/Target Diff show this history? | `handlers[key]()` at `sample/work.py:9` worsens unresolved calls from 0 to 1 (0/2 to 1/1). Its changed dynamic-call UNKNOWN fingerprint also fails a guardrail. Check compares revisions; Actual/Target Diff compares a snapshot with its contract. |

After each task, ask what evidence the reviewer would give a coding agent: source location,
rule/finding identity, unresolved evidence, and the analyzed commit and source/contract binding.
Do not reveal missing items until timing ends.

## Run and record

- Invite 6–8 developers who perform code reviews; record prior Archkeel experience.
- Give the same introduction, questions, browser and viewport. Test keyboard use too.
- Show each case once per participant. Alternate old/new layout assignments by case;
  reverse assignments for alternating participants and rotate task order to limit learning effects.
- Record correct decision, missed UNKNOWNs, false claims, time to a correct source location,
  total time, and handoff completeness. Timeouts and navigation failures remain recorded failures.
- Keep raw anonymous rows: `participant,case,layout,renderer_sha,decision,source,missed_unknown,
  false_claims,source_seconds,total_seconds,handoff_gaps,notes`.

Report raw outcomes and descriptive times per case, without a combined score or a significance
claim from this small pilot. Retain changes only when correctness and uncertainty handling hold.
Record repeated navigation failures before proposing a separate explorer.

## Research basis

- Context and change understanding were central review needs in
  [Bacchelli and Bird, ICSE 2013](https://sback.it/publications/icse2013.pdf).
- A 28-developer experiment found fewer false issue reports from change decomposition,
  without more defects found: [di Biase et al.](https://arxiv.org/abs/1805.10978).
- Graph readability depends on task, size and density; path tasks need suitable interaction:
  [Ghoniem et al.](https://mohammad.ghoniem.info/research/ivs-usability-2005.pdf).
- [dev.fast](https://dev.fast/) supplies source-bound review and agent-copy inspiration.
  It is a product reference, not evidence that Archkeel's layout improves human review.
