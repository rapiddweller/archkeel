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

Never assume that the installed CLI has the `studio` command. A PyPI release before 5.0 has no `studio`.
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
- Scope flags: `--language`, `--source`, `--namespace`, `--tsconfig`, `--agent`; match `explore`'s
  scope. TypeScript and Dart need language options.

The first output line is `ArchKeel Studio: <URL>`. The URL token logs the browser in once.
Studio then sets an `HttpOnly`, `SameSite=Strict` cookie; later requests need that cookie.
Treat the URL as secret. Do not put it in logs or public channels. Share it only with the owner
privately. Same root, scope and agent reuses the server; mismatch exits 2 without a second server.
Stop first to change scope or agent.

## 3. Give the owner the URL

1. Give the full URL, with its token, as a link.
2. Say that the page runs on this computer only.
3. Say that the first explore run can take minutes on a large repository. The Overview shows the progress.
4. Say that the server stops by itself after 60 minutes without a request.

## 4. Stop it

```bash
<archkeel> studio --stop --root <root>
```

It prints `ArchKeel Studio: stopped.` or `ArchKeel Studio: not running.` Exit 1 means cleanup remains
after 15 seconds; starts stay blocked by its marker. For a stale marker, verify no Studio/Explore
for this root remains before removing the printed state file; PID reuse can keep markers alive.
