# Set up Archkeel

Requires Python 3.11+ and a Git repository with at least one commit.

```bash
uv tool install archkeel
archkeel skill install codex    # or claude
```

Use `$archkeel` in Codex or `/archkeel` in Claude Code. Start a new session if the
skill is unavailable. Reinstalling updates its file while preserving unrelated
instructions. The CLI is required even when using a plugin.

## Choose the boundaries

Ask the agent to read architecture documents and inspect packages recursively.
Preserve approved contracts. Confirm the overall design, then decide gaps and
conflicts with source evidence; existing imports are not permission.

1. Run `archkeel init --json`. It drafts configuration, contract and provenance;
   DRAFT is not approval. Existing setup should be restored, not overwritten.
2. Review component ownership and public interfaces. Nonempty namespace
   initializers need explicit `exact_modules` ownership. Future interfaces belong
   in `planned`, not `public`.
3. Record each architect-approved component's responsibility and dependencies. For
   example, add this to the existing storage component without replacing its ownership
   or public fields:

```json
{
  "responsibilities": ["Persist and retrieve domain records."],
  "decided_by": "architect",
  "requires": [
    {
      "component": "domain",
      "rationale": "Storage persists domain records.",
      "decided_by": "architect"
    }
  ]
}
```

Append this to the existing rules. Empty or absent requirements forbid outbound
component pairs:

```json
{
  "id": "REQUIRES-COMPLETE",
  "kind": "complete_requires",
  "rationale": "Each source states its approved outbound dependencies.",
  "provenance": ["docs/architecture/architecture.md"],
  "decided_by": "architect"
}
```

4. Replace structural TODO rationales. Run `archkeel validate --json`; resolve
   open decisions, placeholders and repeated rationales. Run `archkeel report`
   and review findings and the file diff.

Exit 0 means command completion; `declared_rules` can remain FAIL or UNKNOWN.
Fix forbidden crossings or explicitly reconsider intent. Auto mode records
`decided_by: "agent"`, which proves authorship, not human approval. Interview and
auto mode are [skill workflows](../skills/archkeel/SKILL.md), not CLI flags.

For other profiles, use explicit inputs:

```bash
archkeel init --language typescript --source src --namespace app --tsconfig tsconfig.json
archkeel init --language dart --source lib --namespace app
```

See [profile prerequisites and overrides](reference.md) before running them.
Default reports go under `test-artifacts/`; ignore that directory or choose
`--output`.

## Track existing violations

Keep intent and baseline current debt:

```bash
archkeel validate --baseline known-violations.json --write-baseline
archkeel validate --baseline known-violations.json
```

Review the initial file. Known violations remain FAIL. Update resolved debt with
its code change; `--accept-new` needs an explicit decision. Continue with the
[target-first loop](target-first.md). `make demo-onboarding` replays setup with
committed decisions and no live approval. See [reference](reference.md) for plugins
and other commands.
