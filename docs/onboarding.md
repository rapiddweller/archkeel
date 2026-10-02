# Set up Archkeel

Use Archkeel to check the architecture you want, including boundaries the code
has not reached yet. You own those decisions; the agent helps inspect and encode them.

## Install the CLI and skill

Requires Python 3.11+ and a Git repository with at least one commit.

```bash
uv tool install archkeel
archkeel skill install codex    # or claude
```

Use `$archkeel` in Codex or `/archkeel` in Claude Code. Start a new session if needed.
The installer writes `.agents/skills/archkeel/SKILL.md` or
`.claude/skills/archkeel/SKILL.md`. Reinstalling updates that file. For Codex it also
removes the old marked Archkeel section from `AGENTS.md`, preserving other instructions.
Malformed or duplicate markers fail before any files are written.

## Choose the boundaries

Ask your agent:

```text
Set up Archkeel for this repository. Preserve existing contracts.
Read the architecture documents and inspect packages recursively.
Propose the components, public interfaces, and allowed dependencies with source evidence.
Confirm the overall design with me, then ask only about gaps or conflicts.
Record my reasons. Show unresolved findings and the file diff when finished.
```

1. `archkeel init --json` drafts components, interfaces, and open dependency decisions.
   It writes `archkeel.toml`, `architecture-contract.json`, and `docs/architecture/architecture.md`.
2. Decide which directions are allowed. The agent records them as `requires` entries,
   with your rationale and `decided_by: "architect"`. `complete_requires` forbids all absent pairs.
3. Run `archkeel validate --json`. Resolve `decision.open`, `rationale.placeholder`,
   and `rationale.repeated`. Then run `archkeel report` and review the generated files.

Existing imports do not justify allowing them. `rule.violated` means code crosses a boundary
you chose; fix the code or explicitly reconsider the target. Do not keep changing the target
until validation turns green. Review physical packages too, including those without nested
contracts, and record any deferred subtrees. A passed rule does not complete a design review.

You can instead delegate decisions to the agent (**auto mode**). It uses documents first,
confirmed principles next, then clearly labeled judgment, recording `decided_by: "agent"`.
That records authorship, not human approval. Interview and auto mode are skill workflows,
not CLI flags. The [installed skill](../src/archkeel/cli/assets/SKILL.md) contains the full rules.

## Track existing violations

Keep the target and record the current violations:

```bash
archkeel validate --baseline known-violations.json --write-baseline
archkeel validate --baseline known-violations.json    # CI
```

Review the initial file. Known violations remain `FAIL`; the baseline gate rejects new,
increased, or resolved entries that need updating. Rewrite it after fixes in the same change.
Adding violations with `--accept-new` requires an explicit decision.
See the [target-first guide](target-first.md) for baseline and contract maintenance,
and [the reference](reference.md) for command details.

## Install as a plugin

The CLI is still required. After the marketplace files reach the default branch:

```bash
codex plugin marketplace add rapiddweller/archkeel
codex plugin add archkeel@archkeel
```

In Claude Code, run these separately, then use `/archkeel:archkeel`:

```text
/plugin marketplace add rapiddweller/archkeel
/plugin install archkeel@archkeel
```

Codex availability depends on the host. Both plugins reuse the same skill, with no server or hooks.
For local Claude testing, use `claude --plugin-dir .` from this checkout.

### Publish a release

```bash
make plugin OUTPUT=build/archkeel-plugin    # use a new destination
```

This exports the skill, manifests, icon, and license as real files and a ZIP. Git installs
track commits; add a release version to the exported manifest before public submission.
Maintainers submit through [OpenAI's plugin dashboard](https://platform.openai.com/plugins)
and [Claude's directory portal](https://claude.ai/directory/manage). Review and publication are
separate steps; these catalogs alone do not create a public listing. The official Claude
marketplace uses a separate partner route.
See [OpenAI submission](https://developers.openai.com/plugins/deploy/submission) and
[Claude distribution](https://code.claude.com/docs/en/plugins/publish).

## Try the setup without changing your project

`make demo-onboarding` replays the workflow on the shop sample using committed decision fixtures.
It performs no live approvals. See the [demo catalog](architecture-demo.md) for other cases.
