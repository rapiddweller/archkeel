# AD-276 A leading UTF-8 BOM is not source text

**Status.** Proposed. The owner approves it.

**Decision.** The Python collector reads a source file with `decode_source` (`source.py`).
1. It decodes the bytes with `utf-8-sig`. This drops at most one leading byte order mark (BOM)
   and decodes as `utf-8` otherwise. The text and `ast` see no `U+FEFF` at the start.
2. The BOM is not a character. Line 1 starts after it. A column on line 1 equals the column
   of the same file without a BOM. This matches `ast.parse` of the bytes and an editor.
3. The file digest and `source_bytes` still cover the raw bytes, BOM included.
4. A coding cookie is not read, as before. A file in another encoding stays a coverage failure.
5. Two BOMs, or a BOM at the start of a later line or inside a line, stay a coverage failure
   (`SyntaxError`, `invalid non-printable character U+FEFF`). The interpreter rejects them too.
6. The provider capture (`provider_sources`, `collect.py`) uses the same function. A captured
   provider carries text without a BOM. Its digest is `sha256` of that text, because the request
   codec checks `sha256(source.encode("utf-8")) == digest`. Without a BOM nothing changes.

**Reason.** The interpreter accepts a source with a BOM. Editors on Windows write one often.
The collector decoded with `utf-8`, so the BOM stayed as `U+FEFF` and `ast.parse` refused the
whole file (#742). The result was an UNKNOWN coverage failure for each such file, on every Python
version. With a BOM in the importing file and in the imported package `__init__.py`, the demo
variant found no violation (#742).

**Effect on digests.** A provider input with a BOM had a digest over the BOM bytes, and then
failed to parse. It now parses, and its digest covers the text. The digest changes once.
A lock without such a provider does not change. The datetime witness in `calls.py` digests raw
bytes of `datetime.py`. It equals the provider digest because that file has no BOM.

**Rejected.**
- Use `tokenize.detect_encoding` for the cookie. It splits lines at LF only. A CR-only file
  with a BOM and a `coding:` text in a comment was refused, but `compile` accepts it.
- Read the cookie and decode other encodings. This is a separate behaviour change. No evidence
  asks for it.
- Strip every `U+FEFF`, or one at the start of each line. The interpreter rejects these files.
- Keep the digest over the raw bytes for a provider. The request codec refuses it.

**Limits.**
- A BOM with a non-UTF-8 cookie on an LF line is accepted when the text decodes as UTF-8.
  The interpreter raises there. The cookie is not read, so the collector cannot tell.
- A file in another encoding with non-ASCII bytes stays a failure (`UnicodeDecodeError`).

**Check.**
- `tests/test_python_utf8_bom.py`:
  - `test_source_with_a_mark_parses_and_keeps_its_bytes`: no BOM, BOM with code, with a `utf-8`
    cookie, with CRLF and CR, without a final newline, BOM only, and CR-only comment text with
    `coding:`. Each checks text, `source_bytes` and digest.
  - `test_first_line_column_ignores_the_mark`.
  - `test_source_the_interpreter_rejects_stays_a_failure`: two BOMs, BOM at the start of line 2,
    BOM in a line.
  - `test_cookie_without_a_mark_is_decoded_as_before`.
  - `test_whole_pipeline_gives_the_same_verdict_with_and_without_a_mark`: same status and
    evidence (file, line, column, excerpt), BOM in `__init__.py` and in the module.
  - `test_provider_source_is_captured_without_the_mark`: text, digest and request round trip.
- Demo catalog, `fixtures/demo_catalog_dependencies.py`: `class-a-forbidden-dependency-pair-bom`
  gives the verdict of `class-a-forbidden-dependency-pair` with a BOM on the importing file and
  on the imported package `__init__.py`. It fails before AD-276.
- 8 faults are caught: plain `utf-8`, strip every `U+FEFF`, strip at each line start, a
  shifted column, two BOMs stripped, a `detect_encoding` gate, a provider without strip, and a
  provider digest over the raw bytes.
