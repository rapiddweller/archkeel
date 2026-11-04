# AD-292 The Studio chat lets the owner's agent answer read-only; Studio decides what is observed

**Status.** Accepted. Owner decisions of 2026-11-04, epic #783, issues #816 and #822. Slice 3, backend
only, no UI. Builds the `agent` part that AD-290 item 3 planned and adds one route. No route writes.

**Decision.**
1. Component `agent` (`archkeel.studio.agent`) runs one child process at a time, in the root, on the
   sign-in of the owner. Studio passes no key and reads no auth file. The default agent is claude.
   `archkeel studio --agent codex` is an explicit opt-in, with no fallback to the other agent.
   Commands, checked with the installed CLIs on 2026-11-04; prompt on stdin, answer on stdout:
   - `claude -p --tools Read,Grep,Glob --permission-mode dontAsk --no-session-persistence
     --strict-mcp-config --setting-sources user`: no shell, no write tool, a read outside the root
     is denied, the hooks of the repository do not run.
   - `codex exec --sandbox read-only --ephemeral --color never --ignore-user-config -`. Codex runs
     shell commands of the model in its sandbox and can read the whole disk, so it is weaker.
     Its prompt says so: it may run read-only commands and must not read outside the folder.
2. Environment of the child. Claude has no shell: it gets the server environment without the
   variables of a parent agent session and without four API key names (an inherited
   `CLAUDE_CODE_SIMPLE` made `claude -p` fail with "Credit balance is too low"). It keeps
   `CLAUDE_CODE_OAUTH_TOKEN` and the Bedrock and Vertex selectors. Codex gets an allow list only:
   `PATH`, `HOME`, `USER`, `LANG`, `LC_*`, `TERM`, `TMPDIR`, `XDG_*`, `CODEX_HOME`, proxy and certificate settings.
3. One run at a time (409 when busy), 180 s timeout, 128 KiB of stdout. Studio drops stderr, so
   a log with a secret never reaches the answer; a failed run gives a fixed sign-in hint. At the
   end, on timeout, on size and on stop, the process group gets SIGINT; after 3 s it gets SIGKILL
   (POSIX). On Windows only the child is terminated.
4. `git status --porcelain --untracked-files=all` of the root, plus size and mtime of each file it
   lists, is compared before and after the run. If it differs, or git fails (also for a root that
   is no git repository), the answer is discarded (502 `repository_changed`). The edit may stay.
5. `POST /api/v1/chat` checks, in this order: Host and token cookie (403); `Origin` equals the
   server origin (403; `null` fails); header `X-Archkeel-Studio` present (403); Content-Type
   `application/json` (415); Content-Length an ASCII number (411) of at most 16 KiB (413); body
   `{"question": at most 2000 characters, "context": qualified name or null}` (400); `context` is a
   symbol of the snapshot (400); explore is done (503). An error is `{api_version, error, detail}`.
   GET on the route, and PUT, PATCH, DELETE and any other POST, get 405.
6. `/files/*` carries `Content-Security-Policy: sandbox allow-scripts` and `form-action 'none'`
   (the server side of the AD-290 hard gate). The Explorer page has an opaque origin, so a script
   in it cannot reach the parent, the cookie or the chat route. Consequence for the UI team:
   `postMessage` from the page must use target `*`, the parent must check `event.source ===
   iframe.contentWindow` and not `event.origin`, and the parent cannot read `contentDocument`.
7. The prompt is one constant in `agent`: question, selected node, its direct neighborhood (at
   most 30 callers, 30 callees, 10 unknown calls) and the answer shape. No `archkeel` tool.
8. Studio reads `architecture.json` through the canonical decoder that the CLI injects, so the
   format has one reader. The answer is one JSON object, or one fenced block with it, with only
   `blocks` (at most 10). A block has `kind` (`claim` or `proposal`), `text` (at most 2000
   characters) and `refs` (at most 20 strings), nothing else. A break, also a nesting that is too
   deep, gives 502 `invalid_answer`. A ref must equal the `qualified_name` of a symbol. Studio
   drops other refs and lists at most 50 of them, each cut to 300 characters, in `dropped_refs`.
9. `facts` holds, for each valid ref, a record that Studio computes from the snapshot (name,
   file, line, counts of resolved callers, resolved callees and unknown calls). Agent text is never
   OBSERVED. A `proposal` has the label "PROPOSED - NOT APPLIED"; `applied` is `false`; nothing
   applies it. The UI shows `text` as plain text only.
10. API 1.1.0 with `schema/studio-api-1.1.schema.json`; the 1.0 file stays as history. Only
    `workspace` and `agent` import `subprocess`; the pure `answer` module checks the answer.

**Rejected.** An API key. A Bash tool for `archkeel view`. The JSON envelope flags of the CLIs.
Repair of a broken answer. A session or resume. Streaming. A second parser of `architecture.json`.

**Limits.**
- The guard sees only paths that git reports. A write to an ignored path is not seen, and an edit
  of a listed file that keeps size and mtime is not seen. An edit by the owner during a run discards it.
- Claude can read every file below the root, also an ignored `.env`. Codex can read the whole disk.
  The files they read go to the provider of the owner.
- SIGKILL of Studio leaves the child running until it ends; only SIGINT, SIGTERM and Ctrl-C stop it.
- Facts count the calls of the symbol's own scope; a class has no callees. A module is no ref.
- Closing the browser does not stop a run before the timeout. `--idle-exit` waits for a run.
- Verified with one real call each: the flags above and the stdout. Not verified: other versions.

**Checks.** `tests/test_studio_chat.py`, `tests/test_studio.py`.
