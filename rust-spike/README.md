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

## Observed results

- Three Rust tests pass. The target-version negative test checks `UNKNOWN`, an
  incomplete batch and no imports for unsupported syntax.
- One synthetic fixture has eight import occurrences. Their normalized facts and
  positions match CPython's `ast` output.
- The synthetic ProcessCollector child probe reports one coverage gap and zero import
  targets when Python 3.11 syntax is not supported by the parser target.
- No performance claim is measured here. The earlier local project comparison is not
  part of this prototype or its evidence.

## Limits

- A supported parse only proves this syntax slice. Import resolution and re-export
  semantics remain `UNKNOWN`.
- A parser error blocks that file. The prototype does not define how a complete
  versioned batch should report partial work.
- The Rust output is not converted to canonical ArchKeel facts or evidence.
- The parser crate is an internal upstream component. Pin and review upgrades.
- The child-process adapter is an experimental harness, not an approved product path.
