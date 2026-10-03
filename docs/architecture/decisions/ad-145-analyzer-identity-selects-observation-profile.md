# AD-145 Analyzer identity selects the observation profile

An observation's analyzer name selects exactly one profile. The published identities are
`archkeel-python-analyzer` and `archkeel-dart-directives`; every other identity is rejected.
The Python profile requires every section to be an array. The Dart profile emits `null` only
for `symbols`, `references` and `bindings`.

The decoder must not infer Python capabilities from an unfamiliar name. Doing so could turn a
signal the producer never measured into a clean result. Synthetic observations use the same
published identity as the profile they model.

Check: `tests/test_codec.py` covers identity selection, required arrays, Dart null sections and
canonical encoding/decoding.
