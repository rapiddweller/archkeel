# Draft: Rust import parser prototype

This scratch-only prototype is not a supported collector or a finished product API.
It tests one path: parse Python import syntax with Ruff, then pass the batch through
the existing Python collector child process.

## Design

```text
ProcessCollector child
  -> PyO3 wrapper calls Rust import parser with an explicit Python target
  -> UNKNOWN stops that file before Python facts are emitted
  -> CPython AST collector remains the source of facts
```

Rust reports import form, module, name, alias, relative level and source positions.
It does not make IDs, evidence, target resolution, re-export decisions or SQLite writes.
The child-process hook is a probe in this directory. It does not change `src/`.

The SQLite team's versioned `FactBatch` contract is not available here. This prototype
does not define that contract or provide its producer adapter.

## Reproduce on macOS with CPython 3.11

Use Rust 1.97.0, CPython 3.11, and the locked crates. Ruff's parser crates are marked
internal upstream components. Their exact `0.0.21` versions are pinned here.

```bash
PYO3_PYTHON=/usr/local/bin/python \
RUSTFLAGS='-C link-arg=-undefined -C link-arg=dynamic_lookup' \
cargo +1.97.0 test --manifest-path rust-spike/Cargo.toml --locked

PYO3_PYTHON=/usr/local/bin/python \
RUSTFLAGS='-C link-arg=-undefined -C link-arg=dynamic_lookup' \
cargo +1.97.0 build --manifest-path rust-spike/Cargo.toml --locked \
  --bin archkeel-import-facts-spike

PYO3_PYTHON=/usr/local/bin/python \
RUSTFLAGS='-C link-arg=-undefined -C link-arg=dynamic_lookup' \
cargo +1.97.0 build --manifest-path rust-spike/Cargo.toml --locked \
  --lib --features pyo3/extension-module

cp rust-spike/target/debug/lib_core.dylib \
  rust-spike/target/debug/_core.cpython-311-darwin.so
python rust-spike/compare_reference.py
python rust-spike/collector_probe.py
```

`PYO3_PYTHON` must name the same Python ABI that runs the child. Do not load a 3.13
extension in 3.11. The recorded host used `/usr/local/bin/python`, CPython 3.11.12,
and arm64 macOS.

To compare explicit files, call `compare_files.py` with their paths and the Rust binary:

```bash
python rust-spike/compare_files.py \
  --rust-binary rust-spike/target/debug/archkeel-import-facts-spike \
  --target 3.11 path/to/first.py path/to/second.py
```

The runner excludes test paths and prints aggregate categories only. It accepts at most
100 files, limits parser input to 256 KiB per file and 10 MiB total, and gives each parser
call three seconds. It reads one extra byte to detect an input over a limit. The 4 MiB
output limit is checked after capture; it is not a memory limit. It compares Python parser
errors, Rust `UNKNOWN`, and fact mismatches in separate categories. It does not save source
text, file paths or comparison results.

## Observed results

- Four Rust tests pass. The target-version negative test checks `UNKNOWN`, an
  incomplete batch and no imports for unsupported syntax.
- A line-position test covers LF, CRLF and bare CR endings.
- One synthetic fixture has eight import occurrences. Their normalized facts and
  positions match CPython's `ast` output.
- The ProcessCollector child probe uses syntax accepted by CPython 3.11 but unsupported
  by its explicit 3.9 target. It reports one Rust-specific gap and keeps one valid import.
- No performance claim is measured here. The earlier local project comparison is not
  part of this prototype or its evidence.
- The generic file runner is only a tool. No real project scan or output is committed.

## Limits

- A supported parse only proves this syntax slice. Import resolution and re-export
  semantics remain `UNKNOWN`.
- A parser error blocks that file. The prototype does not define how a complete
  versioned batch should report partial work.
- The Rust output is not converted to canonical ArchKeel facts or evidence.
- The parser crate is an internal upstream component. Pin and review upgrades.
- The child-process adapter is an experimental harness, not an approved product path.
