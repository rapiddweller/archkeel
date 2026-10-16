# Nominal amendment artifact

Part of issue #542. The existing IR/governance component owns the immutable amendment value, its supported wire versions, exact contract/baseline binding and the valid/stale verification outcome. `ir.amendment` is model-free; `ir.amendment_codec` uses existing wire validators without adding a model import cycle. Existing widening/governance/codec import paths preserve object identity.

Version 1.0.0 remains contract-only; version 2.0.0 binds both optional baseline digests. Decider and rationale are free text. Both versions preserve their exact sorted, indented UTF-8 bytes and unsupported-version errors. RunResult changes only its amendment_status field; all other controls remain outside this increment.

The authored Target specifies the actual owner fields and API signatures independently of any observed snapshot. Whole-module string-comparison guards cover the artifact and its codec, including protocol dispatch. Model and the remaining governance codec are not claimed migrated. Fixed-Target source-widening and raw equality/membership/match/alias controls demonstrate native enforcement.
