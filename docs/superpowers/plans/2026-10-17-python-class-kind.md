# Python classifier kind implementation plan

Part of #542; approved scope starts at cdcaa7f88537be077a9a44f7002816089ae5cde0.

1. Add a focused failing check for the actual collector's nominal five-value output and one Facts reader, preserving model import identity. Run it against unchanged production code and record assertion failures, not import errors.
2. Move the same enum to Facts, type the actual fixpoint table/set and known-base map, and use one narrow reader at raw/frozen record ingress. Replace the eleven native class-kind literal decisions and the connected SymbolPlacement value-based membership. Keep other record/namespace grammars outside this slice.
3. Pin the canonical owner and reader in authored intent, add the focused suite to durable PR routing, then run focused and existing Python/classifier/boundary/state regressions, strict types/lint, actual native site comparison and true old/new producer wire comparison.
4. Open a separate draft, disclose exact code cost and evidence limitations, and request independent final Astra review. Root owns combined normal baseline/amendment/full-suite integration and the Main steward owns merging.

No new DTO, enum values, module, framework, casts, type-ignore, API-to-policy dependency or resolution ceiling increase. The intended manual production growth is one small reader plus an existing nominal map, with enum relocation counted as a move.
