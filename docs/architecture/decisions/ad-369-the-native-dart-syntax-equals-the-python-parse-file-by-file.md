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

**Problem.** Slice 5 switches the Dart default only when each section equals the Python reply.
The parse decides which files have facts and the gaps of the parse.

**Differences to Python, a closed list (native is equal or stricter).**
- *Depth:* a node deeper than 900 levels gives a syntax concern, so the file has a gap. Python
  stops the whole scan with `RecursionError` near depth 987. This is the closed exception of #880.
- *Surrogate:* a `\uD800` escape in a URI is not a plain string (a `DirectiveError` gap). Python
  keeps a lone surrogate in the target.
- *Combinator:* a combinator that is not `show` or `hide` is a syntax concern. Python raises.
- *Version digits:* a language version with more than 4 300 digits is out of range (a gap).
  Python raises `ValueError` in `int`.

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

**Limit.** Python `\w` is `str.isalnum` or `_`; native uses `char::is_alphanumeric`. The two
differ only on rare marks, such as U+0345, next to a modifier word. No corpus file has one.
`part of` files and sources with no unique owner keep their file fact until slices 4a and 4b.

**Measured (2026-11-11).** Files byte-equal: fixtures 151 of 151, demo variants 295 of 295,
the private app 28 of 28. Bench samples with 240 s of Python time each: `dart-http` 287 of 344,
`flutter` 665 of 6 623. Sections equal on all corpora; on `flutter` 6 619 file facts.

**Tests.** `tests/test_collector_native_dart_syntax.py`,
`tests/test_collector_native_dart_discovery.py`, `native/dart/src/*_tests.rs`,
`native/pytext/src/lib.rs`.
