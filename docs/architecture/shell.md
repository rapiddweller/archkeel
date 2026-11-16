# The Python shell

The Python shell in `src/archkeel` starts the core binary and prints its frame. It decides nothing
([AD-432](decisions/ad-432-the-rust-core-is-the-only-decision-path.md)).
Archkeel checks the shell with its own core and the contract in
`docs/architecture/target/shell-contract.json` (AD-478). Run `make self-validate-shell` to check it.
`make self-validate` checks the shell and `native/`. The pinned rows are in
`docs/architecture/target/shell-expected.json`.

## Parts

| Part | Modules | Task |
|---|---|---|
| `entry` | `archkeel`, `archkeel.cli`, `archkeel.cli.__main__` | Start the command line and return the exit code. |
| `commands` | `core_only` | Send the scan identity, print the frame, map the status to an exit code. |
| `arguments` | `core_arguments` | Read the command line into typed options and refuse by name what this line does not serve (AD-596). |
| `locate` | `core_binary` | Find the core binary of this install. |
| `launch` | `native_scan` | Build the scan request, start the core and return its bytes. |
| `frame` | `core_frame` | Read one frame into typed values. The only part that reads a verdict. |
| `display` | `core_evidence`, `core_explain`, `core_topology` | Decode evidence, the explain part and topology as display values. They give no verdict. |
| `baseline` | `core_baseline` | Read the baseline part of a frame and copy the exit code that the core decided (AD-546). |
| `binding` | `core_binding` | Bind a frame to the request identity and the contract file bytes. |
| `output` | `core_output` | Read the presentation of the core and write the received bytes to one file. |
| `json` | `core_json` | Checked readers and the shared error type. |
| `schema` | `core_schema` | Check a frame against the one schema that the core generates from its types (AD-596). |
| `skill` | `skill` | Install the coding-agent skill. |
| `init` | `init_draft` | Draft `archkeel.toml`, a first contract and its document from the folder layout of a Python project (AD-626). It reads no source. |

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
  mixed-language contract tree is refused (see AD-478).

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    n_0["arguments"]
    n_1["baseline"]
    n_2["binding"]
    n_3["commands"]
    n_4["display"]
    n_5["entry"]
    n_6["frame"]
    n_7["init"]
    n_8["json"]
    n_9["launch"]
    n_10["locate"]
    n_11["output"]
    n_12["schema"]
    n_13["skill"]
    n_0 --> n_6
    n_1 --> n_8
    n_2 --> n_8
    n_3 --> n_0
    n_3 --> n_1
    n_3 --> n_2
    n_3 --> n_6
    n_3 --> n_7
    n_3 --> n_8
    n_3 --> n_9
    n_3 --> n_10
    n_3 --> n_11
    n_3 --> n_13
    n_4 --> n_8
    n_4 --> n_12
    n_5 --> n_3
    n_6 --> n_1
    n_6 --> n_2
    n_6 --> n_4
    n_6 --> n_8
    n_6 --> n_11
    n_6 --> n_12
    n_9 --> n_6
    n_9 --> n_8
    n_10 --> n_8
    n_11 --> n_8
    n_12 --> n_8
```
