# The Python shell

The Python shell in `src/archkeel` starts the core binary and prints its frame. It decides nothing
([AD-432](decisions/ad-432-the-rust-core-is-the-only-decision-path.md)).
Archkeel checks the shell with its own core and the contract in
`docs/architecture/target/shell-contract.json` (AD-474). Run `make self-validate-shell` to check it.
`make self-validate` checks the shell and `native/`. The pinned rows are in
`docs/architecture/target/shell-expected.json`.

## Parts

| Part | Modules | Task |
|---|---|---|
| `entry` | `archkeel`, `archkeel.cli`, `archkeel.cli.__main__` | Start the command line and return the exit code. |
| `commands` | `core_only` | Parse the arguments, send the scan identity, print the frame, map the status to an exit code. |
| `locate` | `core_binary` | Find the core binary of this install. |
| `launch` | `native_scan` | Build the scan request, start the core and return its bytes. |
| `frame` | `core_frame` | Read one frame into typed values. The only part that reads a verdict. |
| `display` | `core_evidence`, `core_topology` | Decode evidence and topology as display values. They give no verdict. |
| `binding` | `core_binding` | Bind a frame to the request identity and the contract file bytes. |
| `output` | `core_output` | Read the presentation of the core and write the received bytes to one file. |
| `json` | `core_json` | Checked readers and the shared error type. |
| `skill` | `skill` | Install the coding-agent skill. |

An arrow points down only. The entry calls the commands, the commands call the other parts, and
no part calls up. Rule `SHELL-REQUIRES-COMPLETE` allows only the arrows in the contract.
`SHELL-NO-*-TO-FRAME` rules name the parts that must not reach the verdict reader.
`SHELL-ONLY-*` rules give each standard-library door (process, arguments, configuration file,
temporary file name, install layout, trace) one home. `SHELL-EXTERNAL-COMPLETE` forbids each
third-party package, so no analysis library enters the shell.

The shell starts the core as a process. That is not an import, so no rule can name the edge
from the shell to the core. `SHELL-ONLY-LAUNCH-STARTS-A-PROCESS` keeps it in one module.

## Rules that the core cannot say today

- A rule that forbids a library that no module imports (`ast`, `tokenize`, `inspect`): the rule
  selects no module, and that makes the scope of the whole run incomplete. Such a rule cannot PASS.
- `external_dependency_scope` with no allowed source: the contract is refused.
- A rule that a module reads no frame field, or builds no `Status` value: there is no rule kind
  for the use of a name inside a function.
- A rule that the shell never imports the Rust crates: they are not Python modules, and a
  mixed-language contract tree is refused (see AD-474).

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    n_0["binding"]
    n_1["commands"]
    n_2["display"]
    n_3["entry"]
    n_4["frame"]
    n_5["json"]
    n_6["launch"]
    n_7["locate"]
    n_8["output"]
    n_9["skill"]
    n_0 --> n_5
    n_1 --> n_0
    n_1 --> n_4
    n_1 --> n_5
    n_1 --> n_6
    n_1 --> n_7
    n_1 --> n_8
    n_1 --> n_9
    n_2 --> n_5
    n_3 --> n_1
    n_4 --> n_0
    n_4 --> n_2
    n_4 --> n_5
    n_4 --> n_8
    n_6 --> n_4
    n_6 --> n_5
    n_7 --> n_5
    n_8 --> n_5
```
