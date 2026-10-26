# AD-272 Rank proven violations on an incomplete observation

**Decision.** This amends AD-258. The ranked list of an unfiltered `report` has three states:

| Observation | Violations in the result | `findings` |
|---|---|---|
| complete | any number | the full list, as before; an empty list means measured empty |
| incomplete | one or more | the violations only |
| incomplete | none | absent (not ranked) |

A filtered report and every other command keep `findings` absent, as before.

Cycles, hubs and budgets stay unranked on an incomplete observation. A violation is proved by
one import site, whatever else is unknown. A claim of absence ("no cycle", "no hub", "no
violation") needs a complete observation.

**Texts.** The three renders (terminal, HTML, JSON) read the same list and add one sentence
when the ranking is partial or missing. The sentence names the reason and the size of the gap.
The fields already exist (`observation_complete`, `coverage`), so the result schema stays 11.0.

| State | Sentence |
|---|---|
| incomplete, with violations | `Only violations are ranked. The observation is incomplete (30 source files could not be resolved), so cycles and hubs are not ranked.` |
| incomplete, no violation | `Findings are not ranked: the observation is incomplete (30 source files could not be resolved). No violation was found in the part that was observed.` |
| filtered | `A filtered result lists no findings. Run report without a filter.` |
| no `findings` key (an older result) | `This result carries no ranked findings.` |

The sentence "No ranked findings: no violation, dependency cycle or hub." is only for an empty
list on a complete observation.

**Reason.** Tung reviewed the Compass fixture (forbidden-edge variant). The header said
FAIL, the rule `data:REQUIRES-COMPLETE` failed, and the Findings section said "No ranked
findings are recorded in this result." The observation had 30 `source_resolution_gap` records,
so `_ranked_findings` returned `None`. The sentence for `None` reads as "nothing found".
The failed rule was the most useful item in the report, and the page hid it. The code
already accepts violations on an incomplete observation for `--only violations`
(`findings_available = complete or declared_rules == "FAIL"`), so this decision only makes the
ranked list follow the same rule. AD-258 does not say that a partial observation ranks nothing;
the sentence is in a docstring only.

**Consequence for the change field (AD-258 slice 2).** A comparison of two revisions covers
only the kinds that both revisions rank. A cycle that one revision ranks and the other does not
is not "resolved"; it is not compared.

**Rejected.**
- Rank cycles on an incomplete observation too. A cycle is a claim of presence, like a
  violation. It is not proved yet that the edges stay sound when imports are unresolved. Add it
  later, after a test shows that they do.
- A new result field (`findings_scope`). The reason is already in the result. A field adds a
  schema version and a consumer rule for no new information.
- Keep `None` and only change the text. The violation would stay hidden.

**Check.**
- The Compass forbidden-edge variant lists the `data` violation and the sentence for a
  partial ranking. The Compass project variant (no violation) has no list and the sentence for
  "not ranked".
- A complete observation gives the same list, the same order and the same bytes as before.
- A filtered report and a command other than `report` keep `findings` absent.
- An empty list on a complete observation keeps the sentence "No ranked findings: no violation,
  dependency cycle or hub." No incomplete observation produces it.
- The terminal, the HTML and the JSON agree on the ranked identities in every state.
- `docs/reference.md` states the three states and that an empty list means measured empty.
