# AD-369 The native Dart syntax equals the Python parse file by file

**Status.** Accepted. Epic #880, PR 8 slice 3a. It follows AD-365 and AD-368.

**Decision.**
1. `archkeel-pytext` holds `str.splitlines` for the Dart and the TypeScript collector. A
   collector crate never uses another collector crate (AD-327), so the clone baseline entry goes.
2. The component `dart-parse` parses each source with `archkeel-dart-grammar` and gives the
   `Syntax` of `analyzer/dart/parse.py` without the sites: the definitions, the directives, the
   concerns, `first_error`, `complete` and the language version. The walk uses no recursion.
3. A source with `first_error` has no file fact and a `SyntaxError` gap. Each other concern is a
   gap with the Python kind (`DirectiveError`, `UnsupportedDeclaration`, `invalid_encoding`,
   `LanguageVersionError`). A source that is not UTF-8 gets `invalid_encoding` and `SyntaxError`.
4. `--dump-syntax` (feature `dump`) prints the syntax of each file. `tools/dart_syntax_parity.py`
   compares it with `dataclasses.asdict(parse(content))`, byte for byte as canonical JSON.
5. L-27: the oracle of each `str` predicate is Python 3.11 with Unicode 14.0.0. The script
   `tools/dart_unicode_tables.py` writes `unicode_tables.rs` from it; `is_word` and `is_space`
   read the tables. Rust `char::is_alphanumeric` differs from `\w` on 15 559 code points. The
   parity tools refuse another interpreter. Slice 3b reads `str.isalnum` from a table too.

**Problem.** Slice 5 switches the Dart default only when each section equals the Python reply.
The parse decides which files have facts and the gaps of the parse.

**Differences to Python, a closed list (native is equal or stricter).**
- *Depth:* a node at depth 900 or deeper gives a syntax concern, so the file has a gap. Python
  stops the whole scan with `RecursionError` near depth 987. This is the closed exception of #880.
  `MAX_DEPTH` must stay below the shallowest depth where a Python walk fails. The review of
  #1055 measured the recursive site walks: closures fail at 170 and local functions at 250
  levels; native flags them at 150 and 230. Each recursive walk of slice 3b gets a parity case
  at its own Python limit.
- *Unicode version (L-27):* a code point that Unicode 14 does not assign gives an
  `invalid_encoding` concern and a gap. Python 3.12 and later read it with newer data.
- *Surrogate:* a `\uD800` escape in a URI is not a plain string (a `DirectiveError` gap). Python
  keeps a lone surrogate in the target.
- *Combinator:* a combinator that is not `show` or `hide` is a syntax concern. Python raises.
- *Version digits:* a version number with more than 4 300 written digits, leading zeros
  included, is out of range (a gap). Python raises `ValueError` in `int`.

**Windows snapshot reads (AD-365) are a gap, not an equal check.** On Windows, Python
`os.path.samestat` compares `st_dev` and `st_ino` of the `lstat` before the open and the `fstat`
after it. Native requires only a regular file after the open, because stable `std` has no file
index. A local process that replaces the source with a link between both calls can make native
read the link target. Python sees the change. The fix is an open with
`FILE_FLAG_OPEN_REPARSE_POINT` (`OpenOptionsExt::custom_flags`) in `archkeel-snapshot`. It must
be in place before slice 5 gives a native Dart PASS on Windows.

**Rejected.** (a) A parse in the records component: the contract forbids it there. (b) One
recursive walk, as in Python: a deep tree overflows the stack and aborts the scan (AD-317).
(c) Port the sites in this PR: they are about 950 of the 2 436 lines, so slice 3b ports them.

**Limit.** `part of` files and sources with no unique owner keep their file fact until
slices 4a and 4b.

**Measured (2026-11-11, oracle Python 3.11.12).** Files byte-equal: fixtures 151 of 151, demo
variants 295 of 295, the private app 28 of 28. Bench samples with 240 s of Python time each:
`dart-http` 287 of 344, `flutter` 665 of 6 623; after L-27, with 90 s: `dart-http` 152 of 152,
`flutter` 200 of 200 and 1 file named by L-27. Sections equal on all corpora; on `flutter` 6 618 file facts.

**Tests.** `tests/test_collector_native_dart_syntax.py`,
`tests/test_collector_native_dart_discovery.py`, `native/dart/src/*_tests.rs`,
`native/pytext/src/lib.rs`, `tools/dart_unicode_tables.py --check`.
