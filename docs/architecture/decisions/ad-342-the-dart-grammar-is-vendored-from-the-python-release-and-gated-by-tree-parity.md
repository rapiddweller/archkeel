# AD-342 The Dart grammar is vendored from the Python release and gated by tree parity

**Status.** Accepted. Epic #880, PR 8 slice 0. The owner decided the grammar source on 2026-11-09.

**Decision.**
1. The crate `native/dart-grammar` (`archkeel-dart-grammar`) vendors the C parser of the sdist
   `tree_sitter_dart-0.1.0.tar.gz` (SHA-256 `5d1566e1…3fdd`, the hash in `uv.lock`). This is the
   fork of efrenbl that the Python collector loads. The crate copies `parser.c`, `scanner.c`, the
   three headers, `grammar.js`, `tree-sitter.json` and `LICENSE` without change. The sdist has no
   `node-types.json`, so the crate has none.
2. Licence: the fork and its upstream (UserNobody14/tree-sitter-dart) are MIT. MIT allows
   vendoring in the MIT distribution of Archkeel. `vendor/LICENSE` keeps both copyright lines.
3. The crate gives one item, `LANGUAGE`, through `tree-sitter-language`. It does not parse. The
   parser is ABI 15, so the workspace keeps one `tree-sitter` (0.25). The crate denies
   `unsafe_code` and allows it only on `LANGUAGE`: the workspace `forbid` cannot be lifted for one
   item. Rule `NATIVE-EXTERNAL-TREE-SITTER-LANGUAGE` keeps `tree-sitter-language` in this crate.
   `tree-sitter` is a dev-dependency only, for the tests.
4. `ARCHKEEL_CODE_DIGEST` also hashes each `.c` and `.h` file under `native/`. The binary links
   the vendored C, so a change of the C must change the digest.
5. Parity gate: `tools/dart_grammar_parity.py` parses each file with the Rust crate and with the
   Python grammar. It compares the full trees: each node in preorder, also each anonymous node,
   with its field, its byte range and its missing and extra flags. A change of the grammar must
   give equal trees on every file.

**Problem.** crates.io `tree-sitter-dart` 0.3.0 gives the tree of the Python collector on 0 of
4 029 files. A native collector on that grammar cannot equal the Python collector.

**Rejected.** (a) crates.io 0.3.0: other trees. (b) A Git dependency on the fork: `deny.toml`
allows crates.io only, and the Python collector loads the PyPI release, not a commit. (c) Compare
`to_sexp()` only: it drops the anonymous nodes and the byte ranges.

**Limit.** The crate has no collector yet; slices 1 to 7 of #880 add it. A new fork release
needs a new vendored copy, the parity gate and an update of `uv.lock` in the same PR.

**Measured (2026-11-11, release build, equal trees / files).** Fixtures and demos 168/168,
a private Flutter app 35/35, bench `dart-http` 344/344, bench `flutter` 6 620/6 620. Parse time
of `flutter`: Rust 18.9 s, Python 21.2 s.

**Tests.** `tests/test_collector_native_dart_grammar.py`, `tests/test_collector_native_digest.py`,
`native/dart-grammar/src/tests.rs`.
