# AD-9 interface profile: measure before implementing

Purpose: before building the `public` interface rule (AD-9), measure how many contract
entries it would add and how exposed the crossing surface already is. `tools/interface_profile.py`
reads an `architecture.json` and its contract and prints these counts; it changes nothing.

## Commands

```sh
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

- Module-first cuts declared lines by roughly 75-78% against a symbol-only scheme in both
  repositories; the `__all__`-or-half rule is doing real work, not a marginal one.
- Module-first keeps the largest declared surface at 7 entries in Archkeel and 11 in the
  service, against 68 and 58 symbol entries; a broad component stays visible as many
  module entries instead of a long symbol list.
- Zero UNKNOWN return/parameter positions on both crossing surfaces means the communication
  table AD-9 proposes would be fully typed from day one - no annotation backlog blocks it.
- Zero underscore crossings on both means `interface_boundary`'s "underscore never qualifies"
  rule would reject nothing that is already relied upon; adopting it costs no rework.
- Max names per edge (55-61) shows a few edges would need large `public` entries; those are
  the modules the half-rule should route to a module entry, not dozens of symbol entries.
- The service's 7 whole-module imports (absent in Archkeel) are the one real gap: `init` must
  default a whole-module use to a module entry, since no per-name usage is observable there.

Conclusion: proceed with AD-9 as specified; the module-first default is worth building, and
no data-quality gap (untyped signatures, underscore reliance) blocks it.
