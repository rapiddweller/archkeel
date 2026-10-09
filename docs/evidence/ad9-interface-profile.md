# AD-9 interface profile: measure before implementing

Historical evidence for [AD-9](../architecture/decisions/ad-09-components-declare-their-interface.md).
Two profiles supported module-first interfaces over long symbol lists; they do
not establish current repository measurements or general accuracy.

`tools/interface_profile.py` reads an observation and contract without changing
either. Run it against a saved report:

```sh
make self-observation
uv run --locked python tools/interface_profile.py \
  --architecture test-artifacts/self-observation/architecture.json --contract architecture-contract.json
```

The tool reports crossing surfaces, proposed public entries and signature limits.
Use `--anonymize` for private repository output. The committed
[internal-service evidence](internal-service/README.md) records the second profile.
For current policy and measurements, use [rules](../rules.md) and
[rule yield](../rule-yield.md).
