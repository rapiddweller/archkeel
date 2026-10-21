# AD-253: SourceFacts V6 pools object keys and repeated values

The accepted #620 SourceFacts payload measured **73,400,708 bytes** in the V5 positional-row format, exceeding the existing 64 MiB collector stdout cap. An offline V6 prototype measured **65,438,889 bytes**, leaving **1,669,975 bytes** of headroom. These are prototype measurements, not the final collection gate or a guarantee for every project. The cap remains unchanged.

SourceFacts protocol 6.0.0 introduces the `source-facts-columnar-v2` envelope:

```json
{
  "encoding": {
    "kind": "source-facts-columnar-v2",
    "key_reference": "<index>",
    "string_reference": "$<index>"
  },
  "facts": "<recursively key-indexed bare V1 rows>",
  "key_table": ["<sorted unique original object keys>"],
  "string_table": ["<sorted unique values selected by lossless interning>"]
}
```

Every object key in `facts` is the canonical decimal index of its original key in `key_table` (`0`, `1`, …; no leading zero). The decoded tree is the existing bare V1 positional-row representation, including its `source-facts-columnar-v1` row marker. String values use the existing `$<index>` references and literal-dollar escaping against the global `string_table`. The decoder rejects noncanonical or duplicate pools, malformed and out-of-range references, key collisions, and noncanonical re-encodings before applying the ordinary SourceFacts row expansion and validator.

The protocol change is transport-only. Expanded V6 facts must equal the same validated SourceFacts model as V5, and compacting V6 back to V1 rows preserves canonical identity. Provider-source survey requests retain the V4/V5 request fields and discovery remains V4; the final Python collection response uses V6 and retains its ordinary `provider_sources` field. Runtime state, provider bindings, contextmanager signatures, and all other semantic checks are validated after expansion. Protocols V1–V5 retain their wire behavior, and no evidence selection, report semantics, or output-size limit changes.

This support change is based on #617 and is intended to land before #619. It supports the catalog transport work in #620 and the wider collector protocol work in #602. The recorded sizes are prototype data; final acceptance depends on the exact full-collection result and installed artifact checks.
