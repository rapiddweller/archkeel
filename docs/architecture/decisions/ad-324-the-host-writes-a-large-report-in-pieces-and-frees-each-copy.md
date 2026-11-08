# AD-324 The host writes a large report in pieces and frees each copy

**Decision.** `archkeel explore` must free each copy of the report when it no longer needs it.
Six changes do this. The output of the command does not change.

1. `write_json` in `ir/codec_wire.py` writes `json.dumps(value, sort_keys=True,
   ensure_ascii=False)` in pieces. It walks four levels of objects. It cuts an array of more
   than 4096 items into slices. `canonical_report_bytes`, `graph_bytes`, `comparison_bytes` and
   `report_bytes` use it.
2. `encode_canonical_model` gets `consume`. Each record section leaves the model when its rows
   exist. `canonical_report_bytes` sets it for the payload that it builds. The row builders move
   to `codec_wire.py` (`section_rows`, `evidence_rows`). Their locals die on return.
3. `intern_strings` makes one `"$n"` string for each table entry.
4. `report_payload` in `ir/graph_codec.py` returns the wire object of a report. `report_bytes`
   writes it and stays in the module. The detail page takes the object. The round trip through
   bytes and a second parse is gone.
5. The Atlas pages hold a mark. `_with_payload` writes the payload at the mark into the buffer
   of the page. The page text never holds the payload. `archkeel.ir.codec` exports `write_json`.
6. `run_explore` deletes the first observation before the second pass starts.

**Contract.** The public list of the root contract names `report_payload` and no longer names
`report_bytes`, because render does not use `report_bytes` any more. `contracts/ir.json` declares
`report_payload` next to `report_bytes`. A v2 amendment binds this and two budget changes.

**Reason.** AD-318 cut the host peak on a React UI (907 files, Linux, 2 vCPU, 2 GiB) from 1 848
to 1 145 MiB. Then three phases peaked together: the encode of the report (1 173 MiB), the report
payload (1 102 MiB) and the detail page (1 229 MiB). The payload text holds two bytes for each
character. Each join made a copy of it. Issue #880 sets the next gate at 1 GiB. The kernel peak
is now 782 MiB, from 1 228 MiB (median of 5 interleaved runs). The host time falls by 5 %.

**Rejected.**
- A streamed render protocol: the CLI would write the pages to files. This changes the contract
  of `render_architecture_pages`. The gate does not need it.
- A smaller report: dropping fields changes a saved format.
- `PYTHONMALLOC=malloc` and `gc.disable()`: AD-318 measured no gain.

**Limit.**
- The decode of the collector reply (about 0.7 GiB) and the second pass (0.77 GiB) do not change.
- `write_json` cuts only the first four object levels and long arrays.
- A key that is not a string makes it write that value with one `json.dumps`.
- `consume` empties the model that it gets. A caller that keeps its model must not set it.
- The page text must hold the mark once. Input that holds the mark raises a `ValueError`.

**Check.** `tests/test_host_memory.py`:
- `write_json` equals `json.dumps` for nested, tuple, empty and non-string-key values. It does so
  with two separators and with slices of 3 items. Its peak stays below 2.5 times the output.
- `encode_canonical_model(..., consume=True)` empties the sections and gives equal bytes. The
  columnar report decodes back to the payload. A payload that the caller owns does not change.
- `report_bytes` equals `json.dumps` of the old wire object, which the test builds with `asdict`.
  The page payload has no `record_ids`.
- `_with_payload` equals the replace of the mark. Input text cannot fake the mark.
- The explore pages carry the payload and no mark. No `Observation` lives at the second pass.
  The collector runs once for both passes.
