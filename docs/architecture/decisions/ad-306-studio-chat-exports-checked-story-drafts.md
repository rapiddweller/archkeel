# AD-306 Studio chat exports checked story drafts

**Status.** Accepted for issue #842.

**Decision.**
1. Chat keeps its existing answer mode and adds an explicit story-draft mode. The agent returns
   only a closed, structured candidate: title and ordered steps with node names and author notes.
   Studio rejects malformed or extra fields. Agent text is never evidence.
2. Studio binds the candidate to the current snapshot and sends it through the injected
   `Stories.check` owner. If the snapshot changes while the agent runs or while the candidate is
   checked, Studio discards the result. The checked ViewSpec is the sole source of proven, claim,
   unknown and missing statuses. Explore-run completeness and View-check source-coverage
   completeness are separate values; the UI labels both and warns when either is incomplete.
   Unknown results remain unknown, never absence.
3. The browser shows the candidate and check together and offers an explicit JSON download. Studio
   adds no route or code path that writes a story or any project file. Existing chat requests keep
   answer mode when the new mode is omitted.
4. API 1.5 pins the additive request and response fields in a new schema. The contract extends only
   the API and its existing agent, answer and server collaborators; Stories remains the checker
   owner. No MCP type, writer, or second story policy is added.

**Rejected.** Treating agent prose or references as proof; accepting agent-supplied verdicts;
writing directly to the repository; duplicating ViewSpec validation.

**Checks.** Fake Claude and Codex answers cover valid and malformed drafts, invented nodes, complete
and incomplete snapshots; the browser exports the checked draft without changing the fixture tree.
