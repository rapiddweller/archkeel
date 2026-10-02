# AD-129: Agent skills use native discovery

## Decision

Install the canonical skill unchanged into `.agents/skills/archkeel/SKILL.md` for Codex
and `.claude/skills/archkeel/SKILL.md` for Claude. Keep the CLI syntax and JSON path result.
Migrate only the old managed Codex AGENTS block; validate markers before writing either file.

Keep the canonical body as a real file at `skills/archkeel/SKILL.md`: Codex skips linked
skill files. The CLI asset links to it; the sdist includes its target so wheel rebuilds work.
`make plugin OUTPUT=...` exports manifests, icon and skill as real files to a directory and ZIP.
Both destinations must be new.

## Why

Native skills expose their description for discovery and load instructions on demand.
Copying the whole skill into AGENTS made it part of every task's instructions.

## Alternatives and limits

Keeping the AGENTS body duplicates active instructions. A server adds a process and
failure modes without a capability the existing CLI lacks. Exported bundles still need the
CLI installed separately. Git-backed Claude versions track commits; a public ZIP needs its
release version added at submission. Manifest checks do not prove host activation or approval.

## Evidence

`tests/test_skill.py` checks native paths, canonical content, idempotency, byte preservation,
malformed/duplicate markers and bundle overwrite rejection. `tests/smoke_test.py` checks
native installation from both built distributions. Codex 0.153.2 and Claude Code 2.1.257
load one namespaced skill from the repository; no personal plugin installation is needed.
