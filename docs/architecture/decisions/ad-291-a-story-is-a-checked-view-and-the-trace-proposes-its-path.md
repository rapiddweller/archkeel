# AD-291 A story is a checked view, and the trace proposes its path

**Status.** Accepted. Issue #822, epic #783. Builds on AD-284, AD-287, AD-289 and AD-290.
Amends AD-284 items 2 and 6: a function can be a node, and a spec can name a story.

**Decision.**
1. View spec `1.2.0` adds an optional `story`: `id`, `title` and `chapters` (`id`, `title`).
   A step then takes `chapter`, `title`, `question` and `external` (`system`, `direction`). The
   step `note` is the story text: it already is author text, so there is no `text` field. These
   fields in a `1.0.0` or `1.1.0` spec are invalid; those specs and their results stay as they
   are. There is no `story check` command: `view check` and `view show` check a story.
2. A chapter id is unique. When the story has chapters, each step must name one. `direction` is
   `reads`, `writes`, `reads_writes` or `touches`. `system` must be in the catalog of item 6.
3. With a `story`, a node can be a function or a method: its qualified name. Without a `story`
   it stays `unknown`, as in AD-284. Two function steps relate by `calls` only.
4. Step status. A step with `claim: true` is `claim`. Otherwise the check reads the call graph:

   | Calls from the step before to the step | Status | Seam |
   |---|---|---|
   | A resolved call to a defined function | `proven`, with each call site | none |
   | A partial call that lists the function as a candidate | `claim`; each call site has `candidates` | `partial_call` |
   | No call; the step before has unresolved, re-exported or truncated calls | `unknown` | `unresolved_call` |
   | No call; a call limit or a module call gap, as in AD-284 | `unknown` | none |
   | No call, and no gap | `missing` | none |

   A claim from the tool does not fail `--strict`, as in AD-284; `candidates` keeps it apart
   from proof. A function next to a module is `unknown`. A process boundary: use a claim.
5. `view check` adds one block, `story`, only for `1.2.0`. For each step, by `index` into
   `steps`: `lane` (the contract component that owns the module, else the second name of the
   module, as `cli` in `shop.cli.main`), `defined_at`, `seam` and `external`. It holds the
   verdict too: counts of steps by status, the systems touched and the modules touched. No PASS
   or FAIL word. Exit codes stay as in AD-284. A missing node is `missing`, not an invalid spec.
6. External systems. One table in `archkeel.ir.flow_graph` maps client libraries to systems:
   redis; sqlalchemy (`relational_database`); pymongo (`mongodb`); boto3, botocore, minio and
   azure.storage (`object_storage`); kafka; pika (`rabbitmq`). A system is touched when the module
   of the step, or the module of a function it calls with a resolved call, imports a module that
   equals a library name or starts with `<library>.`. Evidence is the import site. A
   `TYPE_CHECKING` import and a first-party package of that name do not count. The direction is
   the author claim; `touched` is the observation.
7. `archkeel story trace --from F [--to G] [--snapshot PATH] [--max-paths N] [--max-hops N] --json`
   reads a saved snapshot and prints one JSON document (`schema/story-trace.schema.json`).
   F and G are function or method names. Defaults: 5 paths, 12 hops; at most 100 hops.
   - With `--to`, it lists simple paths from F to G, first over resolved calls only, then over
     resolved and partial calls. Shorter paths come first, then names in order.
   - Without `--to`, it follows resolved calls only and lists the paths to the farthest
     functions: more hops first, then names in order.
   - A hop is `proven` (resolved) or `claim` (partial call, with its seam); an `unknown` hop does
     not exist. Unresolved calls of a function on the path are listed as seams. Each node
     carries its lane, `defined_at` and external touchpoints.
   - No path is exit 0 with `paths: []`. An unknown F or G, or an invalid snapshot, is exit 2.
   - A work limit of 200,000 expansions ends the search: `complete: false`. It says nothing else.

**Reason.** The agent writes only words. The graph gives path, status, lines and lanes, so the
story cannot claim more than the analysis proved.

**Rejected.** A second story format or a `story check` command: the view spec has the nodes.
A `text` field: it duplicates `note`. Free system names. Partial hops as `proven`: they guess.

**Limits.**
- A call through a re-export is unresolved, so a real flow shows some `unknown` steps (AD-284).
- The catalog is small and fixed. A system outside it cannot be claimed. A client two calls
  away is not found. Calls inside a comprehension belong to a scope that is not a function.
- The search lists some paths, not the best path. The step order is not runtime order.
- Loading and validating a snapshot takes most of the time of a run.

**Checks.** `tests/test_cli_story.py`; `test_story_trace_schema_matches_its_dataclasses` and
`test_view_spec_schema_matches_its_dataclasses` in `tests/test_schema_drift.py`;
`test_explain_flow_skill_traces_chooses_writes_and_checks` in `tests/test_skill.py`; demo row
`protocol-story-trace` checks `fixtures/F-architecture-view/order-story.json`
(`test_view_variant_produces_the_catalogued_statuses`).
