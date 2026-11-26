# AD-1115 Install story authoring guidance with the skill

**Status.** Accepted. Builds on AD-291 and AD-1017. Part of issue #1958.

**Decision.** Skill installation creates a narrative template and a view spec 1.2.0 example in
`.archkeel/templates/`. It never replaces either file. The example is not a saved story.
The skill names the Studio search and relations API for exploring calls. It does not claim that
these operations find a complete path. The Explorer guide documents the format and wheel extra.

**Reason.** A new repository has no checked story examples or local authoring guidance.
An agent needs a route to observed calls without the unavailable `story trace` command.
The installed wheel needs the optional MCP extra; checkout-only installation text is not enough.

**Limit.** A copied example needs real node names. A candidate call is not a proven call.
The current Studio chat uses Codex. A Claude Code backend is tracked in #2031.

**Tests.** `tests/test_story_install.py` runs both real skill commands, validates the example
against the view schema and checks that a later installation preserves user edits.
