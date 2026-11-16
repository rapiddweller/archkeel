# AD-612: Remove the unused report v2 pipeline

The core writes the engine frame through `Ruling` and `EngineFrame` (AD-388, AD-432).
The shell and gallery use that frame. No release caller uses the separate report v2 builder,
payload reader or checker. Making their exports private leaves the pipeline without a caller.

Remove the builder, its input and payload types, the checker and their tests. Keep the ruling,
its decided mark, its status rule and the HTML presentation. Keep the proof barrier tests of
the live frame. Move the foreign-pass control to the ruling tests and check the live status rule.

This changes the Rust library API: the removed report v2 exports are no longer available.
The core frame protocol and its HTML presentation do not change. We reject retaining the
pipeline only for its tests. We also reject moving production code behind a test feature.
The historical schema and oracle files remain as records, not as a release interface.
