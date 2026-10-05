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
   For TypeScript, pass a source root, namespace, and project config, for example:

   ```bash
   archkeel init --language typescript --source src --namespace app --tsconfig tsconfig.json
   ```

   For Dart, use `archkeel init --language dart --source lib --namespace app`.
   Repeat `--source` to scan more roots; TypeScript roots may be files or directories. Use
   `--collector-argv node path/to/collector.js` to override the collector command. On Windows,
   pass an executable and script path instead of a `.cmd` shim.
2. Decide which directions are allowed. The agent records them as `requires` entries,
   with your rationale and `decided_by: "architect"`. `complete_requires` forbids all absent pairs.
3. Run `archkeel validate --json`. One `decision.open` diagnostic counts unresolved pairs;
   `open_decisions` holds their evidence. Resolve `decision.open`, `rationale.placeholder`,
   and `rationale.repeated`. Then run `archkeel report` and review the generated files.

For example, after approving `storage -> domain`, add this fragment to the existing
`storage` component. Replace the example reason with the decision owner's actual reason;
keep its existing ownership and public interface fields.

```json
{
  "requires": [
    {
      "component": "domain",
      "rationale": "Storage persists domain records.",
      "decided_by": "architect"
    }
  ]
}
```

Append this rule to the existing `rules` list. An empty or absent `requires` list then
forbids all outbound component pairs; it does not grant observed imports.

```json
{
  "id": "REQUIRES-COMPLETE",
  "kind": "complete_requires",
  "rationale": "Each source states its approved outbound dependencies.",
  "provenance": ["docs/architecture/architecture.md"],
  "decided_by": "architect"
}
```

Review drafted `public` entries and replace each structural rule's TODO with its own real
reason and decision author. A non-empty namespace initializer needs explicit ownership via
`exact_modules`; inspect it before adding that ownership. Rule kinds and selectors are in
the [rule catalog](https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md).

`init` shows DRAFT, even when its scan completed with PASS. Its `measurements.scalars.cycle_edges`
counts observed cycle edge positions; cycles need review, and a cyclic component graph
receives no drafted `no_component_cycles` rule. This advisory is not an error diagnostic.

Read `declared_rules` in both validation and report results: exit 0 means the command
completed, while declared rules can still be FAIL or UNKNOWN. A forbidden direction
produces a FAIL report naming its rule. Add `/test-artifacts/` to your repository’s
`.gitignore` for default report output, or select another location with `--output`.

For a new repository without Git history, run `git init` and create a commit first.
If configuration is missing in an existing setup, restore it or use `--config PATH`;
initialization must not replace an approved contract.

Existing imports do not justify allowing them. `rule.violated` means code crosses a boundary
you chose; fix the code or explicitly reconsider the target. Do not keep changing the target
until validation turns green. Review physical packages too, including those without nested
contracts, and record any deferred subtrees. A passed rule does not complete a design review.

You can instead delegate decisions to the agent (**auto mode**). It uses documents first,
confirmed principles next, then clearly labeled judgment, recording `decided_by: "agent"`.
That records authorship, not human approval. Interview and auto mode are skill workflows,
not CLI flags. The [skill](../skills/archkeel/SKILL.md) contains the full rules.

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

The CLI is required. In Codex:

```bash
codex plugin marketplace add rapiddweller/archkeel
codex plugin add archkeel@archkeel
```

In Claude Code, run these separately, then use `/archkeel:archkeel`:

```text
/plugin marketplace add rapiddweller/archkeel
/plugin install archkeel@archkeel
```

Use `$archkeel:archkeel` in Codex; availability depends on the host. Both plugins reuse the skill.
For local Claude testing, use `claude --plugin-dir plugins/archkeel` from this checkout.

### Publish a release

```bash
make plugin OUTPUT=build/archkeel-plugin    # use a new destination
```

This exports the skill, manifests, icon, license and metadata-derived README as real files
and a ZIP. Git installs track commits; add a release version to the exported manifest before
public submission.
`make plugin-directory` refreshes the committed compact folder. Claude's directory consumes
a Git repository, folder and ref: select `plugins/archkeel` at an approved ref containing it.
The older `0.8.5` tag lacks this folder; the root exceeds a
[Claude component-file limit](https://claude.com/docs/plugins/pre-submission-checklist).
Maintainers submit through [OpenAI's plugin dashboard](https://platform.openai.com/plugins)
and [Claude's directory portal](https://claude.ai/directory/manage). Review and publication are
separate steps; these catalogs alone do not create a public listing. The official Claude
marketplace uses a separate partner route.
See [OpenAI submission](https://developers.openai.com/plugins/deploy/submission) and
[Claude distribution](https://code.claude.com/docs/en/plugins/publish).

## Try the setup without changing your project

`make demo-onboarding` replays the workflow on the shop sample using committed decision fixtures.
It performs no live approvals. See the [demo catalog](architecture-demo.md) for other cases.
