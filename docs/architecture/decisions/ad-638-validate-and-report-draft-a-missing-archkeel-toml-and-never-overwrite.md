# AD-638: `validate` and `report` draft a missing `archkeel.toml` and never overwrite

## Context

AD-626 gave `init`, but a user still had to know it. The owner order: a project without
`archkeel.toml` should get one automatically. The retest also found that `init` printed JSON
only, with no next step, and that `init` read only one Python package.

## Decision

1. `archkeel validate` and `archkeel report` on a Git work tree without `archkeel.toml` (the
   default `--config`) run the logic of `init` first. They write `archkeel.toml` below the work
   tree root, and the contract and its provenance document only if the contract file is missing.
   A file is created exclusively; no existing file is replaced. A failed write removes what that
   run wrote.
2. One block opens the output (text), or the key `init` holds it (JSON): what was written, why,
   and the next step ("ArchKeel created archkeel.toml and a first contract draft with N
   components from your package layout. ... Review the open decisions listed below, then run
   archkeel validate again."). Then the run is a normal run with the new files. The first verdict
   is UNKNOWN with the open decisions, never a PASS and never a refusal.
3. No write: `--no-init`, `ARCHKEEL_NO_INIT=1` (any value but empty, `0`, `false`, `no` or `off`; AD-735), and a folder that
   cannot be written. The run stops with exit 2 (`invalid_input`) and says: no file written, why,
   what the layout would give (language, namespace, components), and `archkeel init` to save it.
4. `init` reads more layouts, by folder layout only (no source): one component per subpackage of
   the one top-level Python package; one per top-level package when there are several (scan root
   `src` or `.`, the namespace is the folder name); one per crate of a Cargo workspace; one per
   member of the `workspaces` of `package.json` (the scan roots are the member folders). The
   modules beside the packages are the component `root` when there are any. A layout that is none
   of these, or that has a Cargo and a package.json workspace at one root, is refused with the
   link to the manual guide. Each component gets the responsibility `TODO`, which the core flags.
5. `init` prints text, also without a terminal; `--json` prints JSON.
6. A custom `--config` that does not exist is not drafted: the core refuses as before.

## Alternatives and limit

- **In-memory configuration** (the run uses the draft without writing). The core reads the
  configuration, the contract and the cited documents as files of the work tree, and the shell
  binds the frame to the contract bytes. An overlay would be a core change with a new soundness
  surface (a verdict for a contract that is not in the repository). Not done: the no-write path
  stops and shows the draft. A later AD can add the overlay.
- Write nothing and refuse (the first design). It leaves the dead end of #1314.
- Python layouts with several packages in a flat root get the namespace of the folder name; a
  folder name with unusual letters is reduced to `[a-z0-9_]`.
- A TypeScript project without `workspaces`, a single Cargo crate and a Dart project are refused.
- The draft is a fact about the folder layout, not about the architecture. The contract's
  dependency decisions stay open; `graph.drift` lists the imports that the core found.

## Checks

`tests/test_cli_auto_init.py`: the block and the verdict for `validate` and `report`; JSON `init`
key; an existing contract and an existing configuration are never changed; `--no-init`, the
variable and a read-only folder write nothing; a layout without a package is refused; plants for
three top-level Python packages, a Cargo workspace and a package.json workspace give one
component per part, no violation and no scope defect; `init` text and JSON.
