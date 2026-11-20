# Local architecture Explorer

Studio and MCP are available from this development checkout. Run `make core` here
before starting Studio. Open a repository with `uv run archkeel studio /path/to/repository`.
Existing scripts can use `explore` as an alias.
Omit the path to use the current repository, or use `--root PATH`. Do not combine both forms.
Without a contract, the Explorer shows observed source and package groups. It does not write a
contract. A project-specific schema file or a gap-free scan is not required to open it. UNKNOWN and partial
coverage remain visible; they do not become a PASS.

The ArchKeel checkout defines three system parts. Select **Python shell**, **Rust core** or
**Studio UI** to inspect its components and modules. To select this contract explicitly, run:

```sh
uv run archkeel studio --config docs/architecture/architecture-system.json
```

Keep the terminal open while you use the browser. Use `--no-open` to print the local
address.

## Follow a dependency to source

1. Choose **Groups** to see the module hierarchy. Open a large group to see its children. Small branches appear inside their parent.
2. Select a module to highlight its incoming and outgoing edges. Choose **Flow →** or **Flow ↓** to change the layout.
3. Read the arrow toward its tip. `A → B` labelled **Import** means A imports B. **Call** means A calls B.
4. Select an edge between two groups. The inspector lists the underlying relations. Select a source reference to open its file and line.

A line can import several names. An import count can exceed the number of source lines.
A call with an unknown target contributes to the unresolved count.
For a Python call with a matching source declaration, Studio can show **Call target · Candidate**.
Open its **Call site** and **Declaration** references to inspect both ends.
The source identifies a possible binding. Python can select another target at runtime.

<img src="assets/studio-call-candidate.png" alt="Studio links a call to IssueDefinition at task_errors.py line 11 to its class declaration at definition.py line 14." width="360">

The unresolved call count can include built-ins, library calls and dynamic calls. A zero count of
recorded sites does not establish call coverage. The arrows do not track values.
Each result includes its snapshot identity and the coverage of the scan.
The System inspector shows how many indexed files in each part have symbol or call records when those counts are available.
It also lists up to 12 external packages resolved from observed imports.
Open a class to inspect its methods and properties. A class card shows a preview of
each group. Each group reports its own collector coverage. A partial inventory can
contain known members. The native report retains its own layout and rule verdicts.

## Play a story

Open **Story**. The ArchKeel checkout includes six examples you can play immediately.
They follow validation to its exit code, report generation to its HTML file, initialization to the
contract files, skill installation to the agent instructions, Studio startup to the browser map,
and an MCP client request to the returned map.

To draft a story, install the Codex CLI and sign in with `codex login`.
Enter the flow you want to follow. The model proposes an ordered story
from snapshot facts. Studio checks each step and saves the story under
`.archkeel/stories/<id>.story.json`. Select **Play** once to follow the calls.
Each lane represents a module. Each step names the function. Pause on a step
to read the explanation and open its source. The cold-cache example follows the
request from Python to Rust, the response back to Python, and the SQLite write.
A dashed transition marks an unresolved link. A follow-up creates
a separate story. Existing stories can be opened without a model connection.

You can share stories and an optional narrative template at `.archkeel/templates/story.md`
with Git. SQLite snapshots stay in the bounded user cache.

## Connect an agent

From this checkout, run the local stdio server with the optional `mcp` extra. Supply the snapshot path from the Explorer and the
absolute path of the scanned repository.

```sh
uv run --extra mcp archkeel-mcp --snapshot /absolute/path/to/snapshot.sqlite3 --root /absolute/path/to/repository
```

The server provides overview, children, search, relations, evidence, source and story.
Use `stories` to list saved stories, `story_read` to play a checked story, and `story_save`
to save a new view specification.
A source request takes a reference from the index. It checks the file content before
returning the excerpt. A call step describes static analysis. Runtime dispatch and
deployment bindings require separate evidence.

## Measure a local corpus

```sh
make explorer-corpus WORKSPACE=/path/to/checkouts OUTPUT=/private/local/results
```

The output can contain private repository paths and source information. Keep it local.
Check the revision, working tree state and scan configuration when comparing results.

## Query a snapshot

The browser uses GET requests under `/api/v1/`. The MCP tools use the same operation
names and element IDs. Every response identifies the snapshot and its coverage.

| Operation | Input | Result |
| --- | --- | --- |
| overview, children | parent (default system), cursor, limit | Elements with ID, name, kind and parent |
| map | parent, view, optional focus, cursor, limit | Use `hierarchy` for the module board. Focus a visible group to inspect its edges. Use `components` or `modules` for a list with a cursor. |
| search | text, optional parent, cursor, limit | Matching elements, or matching modules within a branch |
| relations | element, direction, optional kind, cursor, limit | Directed edges with resolution, element status and evidence |
| relations | aggregate ID from a map edge, cursor, limit | Source relations that contribute to the selected edge |
| evidence | relation | Evidence references and source locations |
| source | reference, limit | Checked lines of the file. HTTP returns 409 if the file changed |
| story | ID of a call edge | One static call step with its evidence, or UNKNOWN |

Lists use a stable ID cursor. Pass the returned `next_cursor` to get the next page.
For Python source candidates, filter `relations` by `kind=source_call`. Each record has
`resolution=candidate`. Its evidence identifies the `call_site` and the `declaration`.
Coverage applies to the selected scan. A null collector section means that this build
does not supply that fact type. An empty section means the collector supplied zero rows.
