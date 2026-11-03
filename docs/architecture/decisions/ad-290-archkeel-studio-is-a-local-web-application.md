# AD-290 ArchKeel Studio is a local web application

**Status.** Accepted. Owner decision of 2026-11-03, epic #783. Amends the "server" part of the
rejected lines of AD-284 and AD-285. The Explorer stays the only renderer.

**Decision.**
1. `archkeel studio [--root PATH] [--no-open]` starts a local server and opens the app in the
   browser. The skill starts it; the owner uses it together with the own agent session.
2. Studio is parallel to the static report, not a replacement. The report stays the CI and Pages
   artifact: contract, deviations, PASS or FAIL and the Explorer. Studio shows those same pages.
   `view show` stays. The tour of #812 becomes the Flows source. The Discussion panel replaces
   the "Ask agent" copy button of #810.
3. Server: stdlib `http.server.ThreadingHTTPServer`, bound to 127.0.0.1 on a free port. No new
   dependency: the wheel already has the pages, and a few routes need no framework.
4. UI: an app shell from `render_studio_page` (`render/html.py`) with no script. Its canvas is an
   `<iframe>` of the explore pages, which are offline and tested (`render/html.py:145-160`).
   A shell script is a new browser source owner (`tools/browser_architecture.py:29-37`).
5. Routes; the root is fixed at start and no route takes a path:

   | Route | Result |
   |---|---|
   | `GET /?token=T` | Sets the cookie, then 303 to `/overview`. |
   | `GET /overview`, `/explore`, `/flows`, `/impact`, `/target` | A shell page. |
   | `GET /state` | JSON: `root_name`, `contract`, `explore`, `seconds`, `exit_code`, `notes`. |
   | `POST /run` | Starts `python -m archkeel.cli explore --root R --json` as a child, 303. |
   | `GET /files/<name>` | One file of the explore output folder, by exact name. |

   Planned: `report --input` per component, view check data, tour, neighbours (#801), impact.
6. Writers. The server writes nothing. The explore child writes only its cache folder
   (`cli/__init__.py:119-122`, AD-285 item 4). Planned, each after an explicit architect click:
   `init` or `init --adopt` (AD-266) creates the contract; `validate --write-amendment` writes an
   amendment. Studio starts those commands and has no second path.
7. Contract state comes from `load_config` (`cli/config.py:216-245`): no file is NOT CONFIGURED,
   a failed load is INVALID, else CONFIGURED. Without a contract, Target says "Target unavailable".
8. Discussion panel (slice 2): for each question, Studio starts the agent CLI of the owner,
   non-interactive and read-only, with the skill: `claude -p --permission-mode plan --tools ...`
   or `codex exec --sandbox read-only --json -C ROOT`. The agent returns data (view spec, tour
   stops, `label` or `responsibilities` text). ArchKeel checks it and marks it "PROPOSED · NOT
   APPLIED". Contract text gets `decided_by: agent` only after the architect accepts it. ArchKeel
   stores no key: the CLI uses the login of the owner. Verified: the flags exist in `--help`.
   Not verified: plan mode blocks each write with `-p`, the exit code without a login, the time.
   Failures: no CLI on `PATH`, no login (show its error), a long answer (cut at 64 KiB or 300 s).
9. Security: 127.0.0.1 only, with no host option. A per-run token (`secrets.token_urlsafe(32)`)
   in the start URL, then an HttpOnly SameSite=Strict cookie. A missing or wrong token, or another
   `Host` header, gives 403. The CSP header allows no other origin: no request leaves localhost.
   No secret scan. No execution of repository code: explore is static.

**Three jobs.** Explain the as-is code: Overview, Explore, Flows. Start a target with the agent:
Target / Diff and the Discussion panel. Adopt the existing architecture as the target: Target /
Diff runs `init --adopt`. Impact: #793. Slice 1 builds Overview and Explore; the rest is "not built".

**Rejected.** A framework (Flask, FastAPI): a new dependency. A React or Vite app: a Node build
for users and a second renderer. An MCP server for the agent: the owner must connect a second
session, and Studio must implement the protocol. A copy-prompt button: no answer comes back to
check. A bind to 0.0.0.0 or a fixed port.

**Limits.** One root, one explore run at a time, one detected Python package (scope options are
planned). Progress is elapsed seconds, not phases.

**Checks.** `tests/test_studio.py` (server, routes) and `tests/test_studio_browser.py` (Chromium).
