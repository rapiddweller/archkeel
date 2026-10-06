# AD-64 `archkeel.api` is the declared external contract, and `ir` performs no I/O

Use `archkeel.api` as the external read facade; keep file I/O out of derivations over consumer
evidence. Internal codecs and component-public entries are not external compatibility promises. One
facade avoids competing supported read paths.

Checker-source digest reads are a separate identity operation.
[AD-70](ad-70-the-external-promise-declares-every-type-it-hands-out.md) narrows the original facade
to `load_violations`. Proof: [test_violations.py](../../../tests/test_violations.py).
