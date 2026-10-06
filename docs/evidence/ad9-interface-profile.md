# AD-9 interface profile: measure before implementing

Before implementing AD-9, `tools/interface_profile.py` measured crossing surfaces
and proposed `public` entries from `architecture.json` and its contract. It changes nothing.

## Commands

```sh
make self-observation
uv run --locked python tools/interface_profile.py \
  --architecture fixtures/D-self/architecture.json --contract architecture-contract.json

# Any other repository: archive a commit into a scratch clone, then observe and report it.
git -C <repo> archive <sha> | tar -x -C <scratch>
git -C <scratch> init -q && git -C <scratch> add -A
git -C <scratch> -c user.email=probe@example.invalid -c user.name=probe commit -qm snapshot
uv run --project <archkeel-checkout> --locked archkeel init --root <scratch>
uv run --project <archkeel-checkout> --locked archkeel report --root <scratch> \
  --output <scratch>/out/architecture.json
uv run --locked python tools/interface_profile.py --anonymize \
  --architecture <scratch>/out/architecture.json --contract <scratch>/architecture-contract.json
```

## Measured profiles

| Metric | Archkeel (7 components) | Internal service (13 components, anonymized) |
|---|---|---|
| Crossing imports | 179 | 620 |
| Edges (component pairs) | 10 | 37 |
| Names per edge (median / max) | 5.5 / 61 | 3 / 55 |
| Surface size per component, symbol-only (median / max) | 4.0 / 68 | 6 / 58 |
| Surface size per component, module-first (median / max) | 3.0 / 7 | 3 / 11 |
| Contract lines, symbol-only total | 87 | 189 |
| Contract lines, module-first total | 22 | 41 |
| Signature positions / UNKNOWN | 145 / 0 (0%) | 63 / 0 (0%) |
| Underscore crossings | 0 | 0 |
| Type-checking crossings | 0 | 0 |
| Whole-module imports | 0 | 7 |

## Go/no-go reading

- Module-first cuts declared lines by roughly 75-78%. Largest surfaces shrink
  from 68/58 symbol entries to 7/11 module entries.
- Both measured surfaces have zero UNKNOWN signature positions and underscore
  crossings. Neither requires annotation or underscore-access rework for AD-9.
- Edges with 55-61 names support the half-rule's module default.
- The service's 7 whole-module imports require `init` to default to module
  entries: per-name usage is unavailable.

These two profiles supported proceeding with AD-9's module-first default.
