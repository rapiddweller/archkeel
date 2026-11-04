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

1. Give qualified names, such as `shop.cli.main.main`. Without `--to`, trace resolved calls to
   the farthest functions. With `--to`, the trace also searches paths with partial calls.
2. Read `paths`. A hop is `proven` (a resolved call) or `claim` (a partial call, with its seam).
3. Read `seams`: an unresolved call is a gap. Name it in the story. Do not hide it.
   Check each call-site file and line in the source before you write its words.
4. Choose one path. Do not invent a hop that no path has. Keep a partial hop as `claim`; use
   `claim: true` only for a needed step with no measured path.

## 3. Write the story spec

Write a view spec with `"schema_version": "1.2.0"`. Add a `story` with `id`, `title` and `chapters`.
List every step node in `nodes`. The `snapshot` digests may stay as the trace gives them: Studio
checks the story by node name and ignores them on a mismatch. For each step in `steps`:

- `node`: a function from the trace.
- `chapter`, `title`, `note` (the story text) and `question` (for the architect): your words.
- `external`: `{"system", "direction"}` only when the owner needs it. The direction is your claim.

## 4. Check it, store it, show it

1. Run `archkeel view check story.json --snapshot <dir>/architecture.json --json`.
2. Read the result, not your spec. Report each `unknown`, `claim` and `missing` step to the owner.
3. If a step is `missing` or `unknown` for no good reason, change the spec. Do not argue with the result.
4. Write the spec to `<root>/.archkeel/stories/<id>.story.json` with your own write tool. This
   stored story is reviewed repository documentation. Add `created` (UTC time), `git_head` (from
   `git rev-parse HEAD`), `author_kind: "agent"` and
   `agent` (your name). Do not edit anything else in the repository.
5. Tell the owner to open Studio (`explore` skill) and pick the story in the list. Studio reads
   the folder and checks the story again on the current snapshot. For a static page run
   `archkeel view show story.json --snapshot <dir>/architecture.json`.

The spec file is author text, a claim. The owner reviews it like documentation, in a pull request.
Say only what `view check` measured. The `verdict` counts steps; it is not approval.
