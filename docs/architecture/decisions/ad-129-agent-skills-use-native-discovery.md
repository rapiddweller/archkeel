# AD-129: Agent skills use native discovery and compact exports

Install one canonical skill as real files in Codex's `.agents/skills` and
Claude's `.claude/skills`. Native discovery loads on demand; AGENTS duplication
burdened every task. Migrate only the validated managed Codex block.

Exports contain real files in new directory/ZIP destinations; distributions retain
the linked canonical source. Bundles require the CLI separately. Manifest checks
cannot prove host activation, approval or human acceptance.

[Installation proof](../../../tests/test_skill.py).
