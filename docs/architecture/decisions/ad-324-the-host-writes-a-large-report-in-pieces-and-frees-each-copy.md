# AD-324 The host writes a large report in pieces and frees each copy

**Decision.** `archkeel explore` must not hold a copy of the report that it no longer needs.
Six changes make this true. The output of the command does not change.

1. `write_json` in `ir/codec_wire.py` writes `json.dumps(value, sort_keys=True,
   ensure_ascii=False)` in pieces. It walks four levels of objects and cuts an array of more than
   4096 items into slices. `canonical_report_bytes`, `graph_bytes`, `comparison_bytes` and
   `report_bytes` use it.
2. `encode_canonical_model` gets `consume`. Each record section leaves the model once its rows
   exist. `canonical_report_bytes` sets it for the payload that it builds. The row builders move
   to `codec_wire.py` (`section_rows`, `evidence_rows`), so their locals die on return.
3. `intern_strings` makes one `"$n"` string for each table entry.
4. `report_payload` in `ir/graph_codec.py` returns the wire object of a report. `report_bytes`
   writes it. The detail page takes the object. The bytes, parse and write round trip is gone.
5. The Atlas pages hold a mark, and `_with_payload` writes the payload at the mark into the buffer
   of the page. The page text never holds the payload. `archkeel.ir.codec` exports `write_json`.
6. `run_explore` deletes the first observation before the second pass starts.

**Reason.** AD-318 cut the host peak on a React UI (907 files, Linux, 2 vCPU, 2 GiB) from 1 848 to
1 145 MiB. Three phases then peaked together: the encode of the report (1 173 MiB), the report
payload (1 102 MiB) and the detail page (1 229 MiB). The payload text holds two bytes per
character, and each join copied it. Issue #880 sets the next gate at 1 GiB. With these changes
the kernel peak is 1 228 MiB before and 782 MiB after (median of 5 interleaved runs), and the
host time falls by 5 %.

**Rejected.**
- A streamed render protocol: the CLI would write pages to files. It changes the contract of
  `render_architecture_pages`. It is not needed for 1 GiB.
- A smaller report: dropping fields changes a saved format.
- `PYTHONMALLOC=malloc`, `gc.disable()`: AD-318 measured no gain.

**Limit.** The decode of the collector reply (about 0.7 GiB) and the observation of the second pass
(0.77 GiB) are not changed. `write_json` cuts only the first four object levels and long arrays.
A key that is not a string makes it fall back to one `json.dumps` of that value. The mark must
appear once in a page. `consume` empties the model that it gets, so a caller that keeps its model
must not set it.

**Check.** `tests/test_host_memory.py`:
- `write_json` equals `json.dumps` for nested, tuple, empty and non-string-key values, with two
  separators and with 3-item slices. Its peak stays below 2.5 times the output.
- `encode_canonical_model(..., consume=True)` empties the sections, gives equal bytes, and keeps
  its error messages. A payload that the caller owns is not changed.
- `report_payload` equals the parsed `report_bytes`; the page payload has no `record_ids`.
- `_with_payload` equals the replace of the mark; a page needs its mark exactly once.
- The explore pages carry the payload and no mark. No `Observation` lives at the second pass.
