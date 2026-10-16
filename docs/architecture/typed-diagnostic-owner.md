# Owned diagnostic values

The ir.diagnostics owner contains the existing diagnostic kinds, codes, immutable diagnostics, source locations and diagnostic exception. model explicitly reexports the same classes. Valid wire spellings and legacy string construction remain supported; real producers and decisions use the canonical enum values.

The diagnostic owner alone has a whole-module native string-control guard. Independent authored Target entries define its enum identities and DTO field/signature intent. Result, comparison, amendment and command control remain separate pending #542 increments; no whole-model guarantee is made.
