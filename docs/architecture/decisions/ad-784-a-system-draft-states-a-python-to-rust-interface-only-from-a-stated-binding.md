# AD-784 A system draft states a Python-to-Rust interface only from a stated binding

**Status.** Accepted. Part of #880, fixes #1612. Found on pydantic (`pydantic` plus its Rust core `pydantic-core`).

**Context.** `init` drafted a Rust part only for a Cargo workspace with two or more crates (`_rust_layout`). A repository with one crate and no `[workspace]`, such as `pydantic-core/Cargo.toml`, got no Rust part and no note. A mixed Python and Rust repository also got no interface between the parts: the draft knew only spec files (OpenAPI, AsyncAPI, proto) as interfaces, each a TODO candidate. The real crossing of such a repository is the extension module that the crate builds and the Python code imports.

**Decision.**
1. A crate that no workspace above it holds (a `Cargo.toml` with `[package]` and no `[workspace]` in a folder above it in the repository) is a Rust part. It has one component for each top module beside the crate root file (`[lib] path`, else `src/lib.rs`, else `src/main.rs`): each `.rs` file and each folder that holds Rust, without `main.rs` and `bin`. The component `root` holds the crate module and its build script. The collector names the crate `<namespace>.<package>`, with `_` for `-`. Test, bench and example targets stay out of the scan (`exclude_test_sources`), as for a TypeScript draft.
2. A crate has a Python binding when the `pyproject.toml` in its folder states `build-backend = "maturin"` and PyO3 (`[tool.maturin] bindings = "pyo3"`, or no `bindings` key and a `pyo3` dependency). The module is `[tool.maturin] module-name`, else the `[lib] name`, else the package name with `_` for `-`: the rule of maturin.
3. A Python part uses the binding when its project is the crate folder, or its `pyproject.toml` names the distribution of the binding in `[project].dependencies` and the `[tool.uv.sources]` entry of that name is the crate folder: `workspace = true` with the folder among `[tool.uv.workspace].members` and not in `exclude`, or `path` to the folder. Names are compared after PEP 503 normalization.
4. Then the draft states the interface from the Python part to the Rust part that holds the crate (a single crate part, or the workspace part of a member). The title names the module; it is no TODO. The schema is the type stub of the module below `python-source` (`<module>.pyi` or `<module>/__init__.pyi`), else the `pyproject.toml` that states the binding.
5. Nothing else makes this interface. An import of a module with the same name, a crate name that looks like a module, or a dependency without a local source states no binding. Only manifests are read, never a source file, so a `#[pymodule]` name is not read. Only the binding part of the shell parses TOML (`SHELL-ONLY-BINDING-READS-CONFIGURATION`), so the draft reads each key in its plain form (`key = "text"`, `key = [..]`, `key = { .. }` on the lines of its `[table]`); another form reads as absent, so it can miss an interface and never make one.

**Consequences.**
- On pydantic the draft has the parts `pydantic` (Python), `tests` (Python) and `pydantic_core` (Rust), and the interface `pydantic -> pydantic_core` with the schema `pydantic-core/python/pydantic_core/_pydantic_core/__init__.pyi`.
- The `init` text says `Interfaces: N stated by a PyO3 binding (AD-784)` for these, and keeps `open (each names a spec file)` for the spec candidates. A single crate repository is named a `Cargo` layout, not a `Cargo workspace`.
- A dependency from a package index (no uv source) gives no interface, because the installed module need not be the code in the repository.
- A maturin project that states no module name and has a `[lib] name` uses the `[lib] name`. PyO3 needs the `#[pymodule]` function to have this name to load the module, so the two agree on a module that loads.

**Rejected.** Matching the import `from pydantic_core import ...` to the crate `pydantic-core` by name: a name is no binding (soundness law), and the draft reads no source. Reading `#[pymodule]` from `lib.rs`: the draft reads only manifests, and maturin states the module name.

**Undo.** Delete `init_binding.py`, the `crates` and `project` fields of `Layout`, `_rust_crate`, `_in_workspace` and `_bindings` in `init_draft.py`; `_rust_layout` then returns `None` without a `[workspace]` again.

**Tests.** `tests/test_cli_init_rust_binding.py`: the single crate part and its components; the stated binding gives the interface and the system run shows it; four forms without a stated binding (no local source, no maturin, `bindings = "bin"`, no dependency) give no interface while the Python code imports the module; a member of a workspace is no part of its own and its binding targets the workspace part.
