# Local architecture Explorer

Open a repository with `archkeel studio /path/to/repository`. `explore` is the same command.
Omit the path to use the current repository, or use `--root PATH`. Do not combine both forms.
Without a contract, the Explorer shows observed source and layout groups. It does not write a
contract. A project-specific schema file or a gap-free scan is not required to open it. UNKNOWN and partial
coverage remain visible; they do not become a PASS.

To open the local checkout against the ArchKeel system, run:

```sh
uv run archkeel explore --config docs/architecture/architecture-system.json
```

Keep the terminal open while you use the browser. Use `--no-open` to print the local
address. Choose **Components** or **Modules**. The module map shows small branches inside
their parent frames. Open a larger branch to inspect its children. Select a module
to follow its incoming and outgoing arrows. Choose **Groups** to see which modules
belong together. Use a horizontal or vertical flow to follow a dependency.
Read each arrow from its source to its target. For an import, the source imports the
target module. For a call, the source calls the target. An UNKNOWN call target has no
arrow. The unresolved count is part of the recorded call sites in that scope.
It can include built-ins, library calls and dynamic calls. A zero count of
recorded sites does not establish call coverage. The arrows do not track values.
Each result includes its snapshot identity and the coverage of the scan.
The System inspector lists up to 12 external packages resolved from observed imports.
Open a class to inspect its methods and properties. A class card shows a preview of
each group. Each group reports its own collector coverage. A partial inventory can
contain known members. The native report retains its own layout and rule verdicts.

## Play a story

Open **Story**. To draft a story, install the Codex CLI and sign in with `codex login`.
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

Install the optional MCP dependency with `uv sync --extra mcp`. Configure a local
stdio server in the MCP client. Supply the snapshot path from the Explorer and the
absolute path of the scanned repository.

```sh
archkeel-mcp --snapshot /absolute/path/to/snapshot.sqlite3 --root /absolute/path/to/repository
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
| map | parent, view, cursor, limit | Use `hierarchy` for the module board. Use `components` or `modules` for a list with a cursor. |
| search | text, optional parent, cursor, limit | Matching elements, or matching modules within a branch |
| relations | element, direction, optional kind, cursor, limit | Directed edges with resolution and evidence |
| evidence | relation | Evidence references and source locations |
| source | reference, limit | Checked lines of the file. HTTP returns 409 if the file changed |
| story | ID of a call edge | One static call step with its evidence, or UNKNOWN |

Lists use a stable ID cursor. Pass the returned `next_cursor` to get the next page.
Coverage applies to the selected scan. A null collector section means that this build
does not supply that fact type. An empty section means the collector supplied zero rows.
