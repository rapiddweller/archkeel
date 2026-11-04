---
name: explain-flow
description: Use when the owner wants a flow of this codebase explained as a story ("how does X run", "walk me through the flow of Y"), with every step checked against the code.
---

# Explain a flow as a checked story

ArchKeel measures the flow. You write only the words. Agent text is a claim, never a fact.
Never write a status, a line number or a system name from memory. The tool gives them.

## 1. Get a snapshot

Run `archkeel explore --root <root> --output <dir> --json`. It writes `<dir>/architecture.json`.
Use a CLI that has `story trace`. Probe it with `archkeel story trace --help`. Use `uvx archkeel`
or `uvx --from git+https://github.com/rapiddweller/archkeel archkeel` when the probe fails.

## 2. Trace the candidate paths

```bash
archkeel story trace --from <function> --to <function> --snapshot <dir>/architecture.json --json
```

1. Give qualified names, such as `shop.cli.main.main`. Without `--to` you get the farthest paths.
2. Read `paths`. A hop is `proven` (a resolved call) or `claim` (a partial call, with its seam).
3. Read `seams`: an unresolved call is a gap. Name it in the story. Do not hide it.
4. Choose one path. Do not invent a hop that no path has. Use `claim: true` for a step you cannot trace.

## 3. Write the story spec

Write a view spec with `"schema_version": "1.2.0"`. Copy `snapshot.source_digest` and
`snapshot.contract_digest` from the trace. Add a `story` with `id`, `title` and `chapters`.
List every step node in `nodes`. For each step in `steps`:

- `node`: a function from the trace.
- `chapter`, `title`, `note` (the story text) and `question` (for the architect): your words.
- `external`: `{"system", "direction"}` only when the owner needs it. The direction is your claim.

## 4. Check and show it

1. Run `archkeel view check story.json --snapshot <dir>/architecture.json --json`.
2. Read the result, not your spec. Report each `unknown`, `claim` and `missing` step to the owner.
3. If a step is `missing` or `unknown` for no good reason, change the spec. Do not argue with the result.
4. Run `archkeel view show story.json --snapshot <dir>/architecture.json`, or open Studio (`explore` skill).

Say only what `view check` measured. The `verdict` counts steps; it is not approval.
