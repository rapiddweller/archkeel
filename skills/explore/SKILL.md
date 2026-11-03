---
name: explore
description: Use when the owner wants to see the codebase map in the browser ("show me the architecture", "open the explorer", "start Studio"), or to stop or reuse a running ArchKeel Studio.
---

# Explore the codebase in ArchKeel Studio

ArchKeel Studio is a local web app. It runs `archkeel explore` on a repository and shows the
measured map in the browser. It writes nothing into the repository.

Agent text is a claim, not a proof. Say nothing about the architecture that Studio did not measure.
For the first-run procedure (overview, flows, a draft contract), use the `archkeel` skill.

## 1. Find the CLI

Never assume that the installed CLI has the `studio` command. PyPI has 4.0.1 only, and it has none.
Try these probes in order. Use the first one that exits 0. Call it `<archkeel>` below.

1. `archkeel studio --help`
2. `uvx archkeel studio --help`
3. `uvx --from git+https://github.com/rapiddweller/archkeel archkeel studio --help`

For probe 3, tell the owner: this install from GitHub is needed until 5.0 is on PyPI.

## 2. Start or reuse the server

Run this command. `<root>` is the repository root. Add the scope options only when needed.

```bash
<archkeel> studio --root <root> --no-open --idle-exit 60
```

- Claude Code: run it as a background Bash command (`run_in_background`). Read the URL from its output.
- Codex: run it outside the sandbox. The server needs a local port.
- Scope options: `--language`, `--source`, `--namespace` and `--tsconfig`. TypeScript and Dart need
  them. Use the same values as for `archkeel explore`.

The first output line is `ArchKeel Studio: <URL>`. A second call for the same root prints
`ArchKeel Studio: <URL> (already running)` with the same URL and starts no second server.
The server keeps the scope options of its first start. To change them, stop it and start again.

## 3. Give the owner the URL

1. Give the full URL, with its token, as a link.
2. Say that the page runs on this computer only.
3. Say that the first explore run can take minutes on a large repository. The Overview shows the progress.
4. Say that the server stops by itself after 60 minutes without a request.

## 4. Stop it

```bash
<archkeel> studio --stop --root <root>
```

It prints `ArchKeel Studio: stopped.` or `ArchKeel Studio: not running.` Both are fine. Exit code 1
means that the server still runs after 15 seconds: tell the owner.
