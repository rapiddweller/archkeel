# AD-596 The core frame has one generated schema and the shell reads it

**Status.** Proposed. Part of #880. It builds on AD-432 (the core is the only decision path),
AD-390 and AD-422 (the shell reads one frame and fails closed) and AD-592 (the shell contract
names each crossing).

**Reason.** The frame `archkeel-core-frame-1` is the one interface between the core and the shell.
The Rust types of `native/report` and `native/core` wrote it, and `core_frame.py` kept hand-written
lists of its keys. Two sources could drift; a new key in the core would be a refusal in the shell,
and a key that the core dropped would stay accepted.

**Decision.**
1. `native/core/src/frame_schema.rs` generates the schema from the types that write the frame
   (`schemars`, the pinned release of the facts crate): the `Ruling` of the report and `Parts` of
   the core. It joins their properties as `engine_frame::write` joins the keys, adds
   `unsupported.rules` and `html`, and closes each object.
2. The file `schema/archkeel-core-frame-1.schema.json` is committed. A core test fails when it
   differs from the generated text; `cargo test -p archkeel-core -- --ignored
   write_the_frame_schema` writes it. The wheel carries it as `archkeel/schema/`.
3. The new shell part `schema` (`core_schema.py`, standard library only) checks each frame against
   that file before the typed read. It supports only the keywords that the generated schema uses
   and refuses any other keyword, so a schema change that it cannot check fails closed.
4. `core_frame.py` has no list of keys any more. The checks of meaning stay in the shell: the
   premise, the explaining rows, the binding to the request and the `self_test.collect` of a scan.
5. `core_only.py` is split at the seam of the command line: the new part `arguments`
   (`core_arguments.py`) reads the options and refuses by name what this line does not serve. The
   rule `SHELL-ONLY-COMMANDS-PARSE-ARGUMENTS` names it.
6. The 30 private-name crossings of AD-592 are gone. The decoding helpers of `core_json` are
   `as_object`, `as_text`, `as_texts`, `as_count`, `as_fields` and `check_measures`; the readers of
   `core_evidence` are `read_details`, `read_locations` and `read_collection_gaps`. Each is public
   and documented in its part.

**Limits.** `sections` items, `self_test.collect` and the `kind` words of `self_test.contract.rules`
are open in the schema: the core writes them as plain values. The nested decoders of the shell
(`core_evidence`, `core_explain`, `core_topology`, `core_baseline`) still list their own fields
beside the schema; the schema now refuses a wrong shape first. The refusal on stderr
(`archkeel-core-refusal-1`) is a second, separate protocol with its own list in `read_refusal`.
