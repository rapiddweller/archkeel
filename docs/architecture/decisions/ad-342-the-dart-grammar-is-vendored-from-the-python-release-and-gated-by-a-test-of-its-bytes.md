# AD-342 The Dart grammar is vendored from the Python release and gated by a test of its bytes

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
5. Gate (amended for #1031): the vendored bytes are pinned by a test, and a source that the grammar
   cannot parse soundly is a named gap. `native/dart-grammar/src/tests.rs` hashes each file of
   `vendor/` against the table of `vendor/README.md` (a changed, new or missing file fails) and pins
   the parser ABI of the runtime. It runs in `cargo test`, so in `make native-check`.
   `tests/test_cli_native_dart_grammar_gate.py` plants a syntax error, a missing token, invalid UTF-8
   and an out-of-range `@dart` line: each gives UNKNOWN for each import rule with an
   `exception_gap` that names the file and the cause, never a PASS. The collector turns each error
   and each missing node of the tree into the gap (`parse.rs`).
6. `tools/dart_grammar_parity.py` stays as a manual check for a new vendoring. It compares full
   trees with the PyPI release (preorder, anonymous nodes, fields, byte ranges, flags). It is no
   gate: the Python collector is deleted (AD-432), so no decision path loads that grammar.

**Problem.** crates.io `tree-sitter-dart` 0.3.0 gives the tree of the Python collector on 0 of
4 029 files. A native collector on that grammar cannot equal the Python collector.

**Rejected.** (a) crates.io 0.3.0: other trees. (b) A Git dependency on the fork: `deny.toml`
allows crates.io only, and the Python collector loads the PyPI release, not a commit. (c) Compare
`to_sexp()` only: it drops the anonymous nodes and the byte ranges.

**Limit.** A new fork release needs a new vendored copy, a new hash table, one run of the parity
tool and an update of `uv.lock` in the same PR. The tree of an accepted source is not proved
sound: only an error or missing node, a language override outside 2.12 through 3.12 and an SDK
constraint outside that range give a gap (AD-387). A `pubspec.yaml` with no `sdk:` constraint
is no gap: the verdict of the project stays.

**History (#1031).** The Python collector loaded the platform wheels of `tree-sitter-dart` 0.1.0
with tree-sitter 0.26.0 while the crate links 0.25.10. Trees were measured equal only against the
macOS wheel. Both comparisons are obsolete: no decision path has a Python parser. The runtime of
the crate is pinned by the ABI test and by `Cargo.lock`.

**Measured (2026-11-11, release build, equal trees / files).** Fixtures and demos 168/168,
a private Flutter app 35/35, bench `dart-http` 344/344, bench `flutter` 6 620/6 620. Parse time
of `flutter`: Rust 18.9 s, Python 21.2 s.

**Tests.** `native/dart-grammar/src/tests.rs`, `tests/test_cli_native_dart_grammar_gate.py`,
`tests/test_collector_native_digest.py`.
