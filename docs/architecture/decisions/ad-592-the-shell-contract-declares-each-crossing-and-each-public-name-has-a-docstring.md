# AD-592 The shell contract declares each crossing and each public name has a docstring

**Status.** Proposed. Part of #880. It builds on AD-432 (the core is the only decision path) and
AD-478 (the shell has its own contract).

**Reason.** The contract of the Python shell named the parts and their `requires` edges but no
name that a part offers. A part could use any name of another part, also a private one. Many public
names had no stated responsibility.

**Decision.**
1. `docs/architecture/target/shell-contract.json` is on schema 3.14.0. No rule changed in meaning.
2. Each of the 11 parts has `public`: the names that other parts really import, and no more. The
   part `entry` has an empty list: no part imports it (`archkeel.cli:main` is reached by the script
   entry of `pyproject.toml`, not by an import).
3. The rule `SHELL-INTERFACE-BOUNDARY` (`interface_boundary`) fails an import of a name that the
   target part does not declare.
4. The shell reaches the core through one interface: the JSON frame `archkeel-core-frame-1` (and
   the refusal `archkeel-core-refusal-1` on stderr), read only by the part `frame`.
5. Ruff checks `D100` to `D104` (a missing docstring of a public module, class, function, method or
   package) for `src/`. Tests, fixtures, tools and native are outside this rule. No other style rule
   of pydocstyle is on.

**Measured.** 30 crossings use a private name (`_count`, `_fields`, `_object`, `_text`, `_texts`,
`_check_measures` of `core_json`; `_collection_gaps`, `_details`, `_locations` of `core_evidence`).
They are pinned in `shell-expected.json` with issue 880. They are code problems: the helpers are the
decoding API of the shell and need a public name. The contract is not weakened for them.

**Open.** The frame has no schema file. `core_frame.py` holds a hand-written field allowlist beside
the Rust writer in `native/report`. The files `schema/command-result-*.schema.json` describe the
Python commands of 4.0.1, not this frame. One source of truth for the frame is a core-side change.
