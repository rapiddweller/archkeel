# AD-2 JSON has one type

Use `RawJson` at JSON boundaries and narrow it with `isinstance` before constructing typed records.
Keep `Any` only where an actual heterogeneous boundary requires it, with a named rationale. This
keeps unchecked payloads from spreading into evaluation without adding wrappers that prove nothing.

Boundary type: [model.py](../../../src/archkeel/ir/model.py).
