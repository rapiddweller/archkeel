# AD-598 The shell reads no field list and the frame schema is closed

**Status.** Proposed. Part of #880. It closes the limits of AD-596.

**Reason.** AD-596 made the frame schema the one source for the top-level keys, but the nested
decoders of the shell (`core_evidence`, `core_explain`, `core_topology`, `core_baseline`,
`core_output`) and `read_refusal` still listed their own field names, and two parts of the frame
(`sections`, `self_test.collect`) were open `serde_json::Value`.

**Decision.**
1. The Rust types are the one source. `Collect` (`derived` request with `contract_files`, or
   `refused`) and `SectionRow` (the envelope of each section row) are typed in
   `native/core/src/frame_parts.rs`. `request` takes the schema of the facts type `Request`. A row
   that does not fit the envelope is an error before the frame is written.
2. The refusal on stderr is the typed `refusal::Refusal`. Its schema,
   `schema/archkeel-core-refusal-1.schema.json`, is generated beside the frame schema and a core
   test compares both files with the generated text.
3. `core_schema.py` checks a frame and a refusal against these files. Every decoder of the shell
   calls `as_object` and reads the names it needs. No decoder holds an allowed-field list: the
   schema already refused a missing or an unknown field. `as_fields` and the lists are deleted.
4. The meaning checks stay in the shell (counts against budgets, closed paths, explaining rows, the
   premise, the binding, the kind word of a refusal).

**Limits.** `SectionRow.data` stays an open object: it is the payload of each row kind that the
harness compares with the reference engine, and a scan writes no section row. The explain budgets
(`BUDGETS` in `core_explain.py`) are values that the shell compares, not field names.
