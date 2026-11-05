# AD-302 Studio Briefing leads with component facts

**Status.** Accepted for issue #815. Builds on AD-290, AD-298 and AD-301.

**Decision.**
1. The Briefing shows at most six components, ordered by module count, then function count. Each card opens the component view. A link opens the full Architecture map.
2. A source badge scopes contract evidence to declared groups. Each card marks measured counts. Cards count symbols with unknown calls; the global unknown figure counts call sites.
3. The lead keeps the repository, revision and contract status visible. Component cards follow the snapshot status and precede totals. At 800 × 600, the first card stays visible. Detailed patterns stay collapsed.
4. Incomplete snapshots keep their status, notes and measured UNKNOWN total. A failed or missing graph shows no measured facts.
5. An empty graph states that it has no components. Studio does not invent cards.

**Reason.** The long pattern list pushed component facts below the first screen. Users need a short map of the measured structure before optional patterns.

**Rejected.** A second API, an agent summary, or a second renderer. The graph and model already provide the facts.

**Limits.** The six cards rank by size, not architectural importance. The full map contains every component.

**Checks.** `tests/test_studio_browser.py` at 800 × 600 and 1440 × 900.
