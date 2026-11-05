# AD-292 The Studio chat lets the owner's agent answer read-only

**Status.** Accepted on 2026-11-04 for epic #783 and issues #816/#822. Slice 3 adds the backend agent component
and one route from AD-290. No route writes.

**Decision.**
1. `archkeel.studio.agent` runs one child in the root, on the owner's sign-in. Claude is the
   default. Codex requires `archkeel studio --agent codex`; there is no fallback. Prompt uses stdin;
   JSON answer uses stdout. Commands were checked on 2026-11-04:
   - `claude -p --tools Read,Grep,Glob --permission-mode dontAsk --no-session-persistence
     --strict-mcp-config --setting-sources user`: no shell or write tool; outside-root reads are
     denied and repository hooks do not run.
   - `codex exec --sandbox read-only --ephemeral --color never --ignore-user-config
     -`: its shell can read the whole disk; the prompt forbids reads outside the root.
2. Claude gets the server environment without parent-agent variables or
   `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY` or `CODEX_API_KEY`. It keeps
   `CLAUDE_CODE_OAUTH_TOKEN` and Bedrock/Vertex selectors; `CLAUDE_CODE_SIMPLE` breaks `claude -p`.
   Codex gets only `PATH`, `HOME`, `USER`, `LANG`, `LC_*`, `TERM`, `TMPDIR`, `XDG_*`,
   `LOGNAME`, `CODEX_HOME`, proxy and certificate settings. Studio reads no auth files and passes no key.
3. One run at a time (409), 180 s timeout, 128 KiB stdout. Drop stderr and return a fixed sign-in
   hint on failure. On timeout, size limit or stop, send process-group SIGINT, then SIGKILL after
   3 s on POSIX; Windows terminates only the child.
4. Compare root `git status --porcelain --untracked-files=all` and listed-file sizes/mtimes before
   and after the run. If Git fails or the state changes, discard the answer (502 `repository_changed`).
5. `POST /api/v1/chat` checks, in order: Host/token cookie (403), Origin equals the server origin
   (403; `null` fails), required `X-Archkeel-Studio` (403), Content-Type `application/json` (415),
   and ASCII-digit Content-Length (411; over 16 KiB is 413). Only `question` text (1–2000 chars)
   and optional `context` (qualified name or null, max 300 chars) are allowed (400). Context must
   name a snapshot symbol (400); no readable snapshot gives 503. Errors are
   `{api_version, error, detail}`. Only POST is allowed; other methods return 405.
6. `/files/*` uses `Content-Security-Policy: sandbox allow-scripts` and `form-action 'none'`.
   Its Explorer iframe has an opaque origin: it cannot reach the parent, cookie or chat route.
   UI messages target `*`; the parent checks `event.source === iframe.contentWindow`, never origin,
   and cannot read `contentDocument`.
7. One prompt constant carries the question, selected node, direct neighborhood (30 callers,
   30 callees, 10 unknown calls maximum) and reply shape. It provides no `archkeel` tool.
8. Studio reads `architecture.json` through the CLI-injected canonical decoder. Accept one JSON
   object, or fenced JSON, with only `blocks` (max 10). Each block has `kind` (`claim` or
   `proposal`), `text` (max 2000 chars) and `refs` (max 20 strings). Reject malformed or deeply
   nested answers with 502 `invalid_answer`. A ref must exactly match a symbol's `qualified_name`;
   drop other refs and return at most 50, cut to 300 chars each, in `dropped_refs`.
9. Studio computes `facts` for valid refs from the snapshot: name, file, line, resolved caller and
   callee counts, and unknown-call count. Agent text is never OBSERVED. Proposals say
   `PROPOSED - NOT APPLIED`; `applied` is false. The UI renders text as plain text.
10. API 1.1 uses `schema/studio-api-1.1.schema.json`; API 1.0 stays as history. Only `workspace`
    and `agent` import `subprocess`; pure `answer` checks the reply.

**Rejected.** API keys, a Bash tool for `archkeel view`, CLI envelope flags, answer repair, sessions,
resume, streaming and a second parser for `architecture.json`.

**Limits.** The guard misses ignored paths and listed-file edits that keep size and mtime; an edit
during a run discards the answer but may remain. Claude can read every root file, including ignored
`.env`; Codex can read the whole disk. Read data goes to the provider. SIGKILL of Studio leaves its
child running; SIGINT/SIGTERM/Ctrl-C stop it. Facts count calls in a symbol's scope; classes have
no callees and modules cannot be refs. Closing the browser does not stop a run; `--idle-exit` waits.
Each CLI was verified with one real call; other versions are unverified.

**Checks.** `tests/test_studio_chat.py`, `tests/test_studio.py`.

**Amendment for issue #841 (2026-11-05).** API 1.4 keeps schema 1.3 as history. State names the
allow-listed agent before a question; each answer names its agent and snapshot completeness.
Readable incomplete snapshots may answer read-only. Prompt and UI label evidence as snapshot-local.
An exact ref proves only name membership, not meaning. A dropped ref means only that the name was
not listed; an incomplete snapshot cannot prove absence. Studio reports only existing positive facts,
preserves UNKNOWN and never applies proposals. Missing-agent and sign-in errors give useful detail
without exposing stderr. `tests/test_studio_chat.py`, `tests/test_studio.py` and
`tests/test_studio_browser.py` cover this behavior.

The API owns typed `SnapshotCompleteness`. Workspace derives it from Explore; the snapshot index
carries it into checked answers; the agent uses it to qualify its prompt.
