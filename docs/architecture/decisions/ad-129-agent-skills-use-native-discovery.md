# AD-129: Agent skills use native discovery and compact exports

## Decision

Install the canonical skill unchanged into `.agents/skills/archkeel/SKILL.md` for Codex
and `.claude/skills/archkeel/SKILL.md` for Claude. Keep the CLI syntax and JSON path result.
Migrate only the old managed Codex AGENTS block; validate markers before writing either file.

Keep the canonical body as a real file at `skills/archkeel/SKILL.md`: Codex skips linked
skill files. The CLI asset links to it; the sdist includes its target so wheel rebuilds work.
`make plugin OUTPUT=...` exports manifests, icon, skill, license and a metadata-derived README
as real files to a directory and ZIP. Both destinations must be new. `make plugin-directory`
refreshes `plugins/archkeel` through that exporter; directory submissions select this folder
at an approved Git ref. The root includes a self-observation file over Claude's 5 MiB limit.

## Why

Native skills expose their description for discovery and load instructions on demand.
Copying the whole skill into AGENTS made it part of every task's instructions.

## Alternatives and limits

Keeping the AGENTS body duplicates active instructions. A server adds a process and
failure modes without a capability the existing CLI lacks. Exported bundles still need the
CLI installed separately. Git-backed Claude versions track commits; the older `0.8.5` tag
does not contain this folder. A public ZIP needs its release version added at submission.
Manifest checks do not prove host activation, directory approval or a human pilot.

## Evidence

`tests/test_skill.py` checks native installation, canonical bytes, idempotency, invalid markers,
overwrite rejection, compact-folder drift and bundle contents. `tests/smoke_test.py` checks both
built distributions. Codex 0.153.2 and Claude Code 2.1.257 loaded one namespaced repository skill
without a personal plugin installation.
