# AD-292 The Studio chat lets the owner's agent answer read-only; Studio decides what is observed

**Status.** Accepted. Owner decisions of 2026-11-04, epic #783, issues #816 and #822. Slice 3, backend
only, no UI. Builds the `agent` part that AD-290 item 3 planned and adds one route. No route writes.

**Decision.**
1. Component `agent` (`archkeel.studio.agent`) runs one child process at a time, in the root, on the
   sign-in of the owner. Studio passes no key and reads no auth file. `archkeel studio --agent
   claude|codex` names the agent to try first; the default order is claude, then codex. Studio uses
   the first one on `PATH`. Commands, checked with the installed CLIs on 2026-11-04; prompt on
   stdin, answer on stdout:
   - `claude -p --tools Read,Grep,Glob --permission-mode dontAsk --no-session-persistence
     --strict-mcp-config --setting-sources user`: no shell, no write tool, a read outside the root
     is denied, the hooks of the repository do not run.
   - `codex exec --sandbox read-only --ephemeral --color never --ignore-user-config -`.
2. The child gets the environment of the server without the session variables of a parent agent and
   without API keys. A `CLAUDE_CODE_SIMPLE` from a parent session made `claude -p` fail with
   "Credit balance is too low". The explore skill starts Studio from an agent session.
3. One run at a time (409 when busy), 180 s timeout, 128 KiB output. At the end, on timeout, on size
   and on stop, the whole process group gets SIGINT; after 3 s it gets SIGKILL (POSIX). On Windows
   only the child is terminated.
4. `git status --porcelain --untracked-files=all` of the root runs before and after the run. If the
   output differs, or git fails, the answer is discarded (502 `repository_changed`).
5. `POST /api/v1/chat` checks, in this order: Host and token cookie (403); `Origin` equals the
   server origin (403); header `X-Archkeel-Studio` present (403); Content-Type `application/json`
   (415); Content-Length present (411) and at most 16 KiB (413); body `{"question": string of at
   most 2000 characters, "context": qualified name or null}` (400); `context` is a symbol of the
   snapshot (400); explore is done (503). An error is `{api_version, error, detail}` with a
   `ChatError` code. GET on the route, and PUT, PATCH, DELETE and any other POST, get 405.
6. The prompt is one constant in `agent`. It holds the question, the selected node, its direct
   neighborhood from the snapshot (at most 30 callers, 30 callees, 10 unknown calls) and the answer
   shape. The agent gets no `archkeel` tool: it reads files and searches, nothing else.
7. Studio reads `architecture.json` through the canonical decoder that the CLI injects into the
   workspace, so the format has one reader. The answer is one JSON object, or one fenced block with
   it. Only `blocks` (at most 10) is allowed. A block has `kind` (`claim` or `proposal`), `text`
   (at most 2000 characters) and `refs` (at most 20 strings), nothing else. A break gives 502
   `invalid_answer`. A ref must be the `qualified_name` of a symbol. Studio drops an unknown ref and
   lists it in `dropped_refs`.
8. The response has `facts`: for each valid ref, a record that Studio computes from the snapshot
   (qualified name, file, line, counts of resolved callers, resolved callees and unknown calls).
   Agent text is never an OBSERVED fact; it stays a claim. A `proposal` block reads
   "PROPOSED - NOT APPLIED", the response has `applied: false`, and nothing applies it.
   The AD-290 hard gate still holds for any route that writes.
9. API 1.1.0: `schema/studio-api-1.1.schema.json` pins the state, the request, the response and the
   error. The 1.0 file stays as history. AD-290 item 4 is amended. The generated UI vocabulary and
   bundle change only in the version string.
10. Enforced: only `workspace` and `agent` import `subprocess`; the pure `answer` module builds the
    snapshot index and checks the answer; the server starts no process.

**Rejected.** An API key. A Bash tool for `archkeel view` (a shell can write). The JSON envelope
and schema flags of the CLIs (text and exit code are enough). Repair of a broken answer. A session
or resume (each question stands alone). Streaming (no UI yet). A second parser of `architecture.json`.
A flag name `--engine`.

**Limits.**
- The guard sees only paths that git reports. A write to an ignored path, or a second edit of a
  file that is already modified, is not seen. An edit by the owner during the run discards it.
- The agent can read every file below the root, also an ignored `.env`. The files it reads go to
  the provider of the owner.
- The Explorer iframe is same-origin and can reach the route through `parent.fetch`. The AD-290
  sandbox gate closes this before any write route.
- Facts count the calls of the symbol's own scope; a class has no callees. A module is no ref.
- Closing the browser does not stop a run before the timeout. `--idle-exit` waits for a run.
- Verified with one real call each: the `claude` and `codex` flags above and the stdout. Not
  verified: other versions, and the quality of real answers.

**Checks.** `tests/test_studio_chat.py`, `tests/test_studio.py`.
