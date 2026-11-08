# AD-320 The native collector records import statements with the grammar of the Python collector

**Decision.** PR 4.2 of issue #880 gives `archkeel-typescript-collector` module resolution and one
import record for each import statement, with its target, in the protocol 8 reply of AD-316. The
capability stays legacy. These facts are not the Python default: the Python collector stays the
default until PR 4.4. The Python collector is also the oracle, in a mode that PR 4.3 deletes.

1. The parser is `tree-sitter` 0.25 with `tree-sitter-typescript` `=0.23.2`, the grammar release
   of Python. A review mutated 3 000 files: both gave the same tree and `has_error`. oxc and swc
   have no ERROR nodes, so they cannot give the same references. `Cargo.lock` pins
   `tree-sitter-language` 0.1.5 (0.1.9 needs Rust 1.90) and grows by 15 packages.
2. One walk over the tree finds the nodes. `parse.py` runs seven queries, and each walks the
   whole tree. `scan_tests.rs` keeps the seven queries as the reference and compares both.
3. The forms are `import`, `export ... from`, `import x = require()`, `import()`, `import type()`
   and `require()`. A reference inside a repaired region is not a fact. A computed specifier is a
   gap, and so are a syntax error, a Node loader, an indirect `require` and a JSDoc import.
4. The resolver and the compiler options follow `resolve.py` and `config.py`. A value that is not
   understood makes the settings partial, and a partial setting resolves nothing. Each
   `package.json` that the resolver reads is a digested input, so the inputs equal the Python inputs.
5. The nesting of a source cannot overflow the stack: the walk is iterative. A file with 30 000
   nested brackets gives a result. Python stops with a `RecursionError` at 1 000. Caps with a gap
   and its reason belong to the memory limit of PR 4.1b-3.
6. A non-test source file holds no `unwrap` and no `expect` (clippy `deny`), because a panic
   aborts the whole scan.

**Acceptance.** The oracle is `tests/native_oracle.py`: the Python collector with the four
producers off that the native collector does not have (`_named_imports`, `_script_dependencies`,
`_inner_facts`, `_constructs`). No result is filtered by a title. These are all the allowed
differences. A tree with a global script file fails the test. The files, inputs, evidence,
records, targets, gaps and coverage must be equal. The host verdict, the cycles and the
violations must be equal on the fixtures and on 53 demo variants. Two runs give the same bytes.

**Reason.** The host accepts three capability sets (`evaluate.py`). A record with `symbols_known`
needs facts in `bindings`, so it needs the inner UML set, which would state that a file has no
symbols. The native scan cannot prove that. Measured on macOS with 10 interleaved runs, 910 files:
the full Python collector 100.5 s, Python parse with the same seven queries 2.05 s, native with
the queries 1.94 s, native with one walk 1.02 s.

**Rejected.** A scanner by hand. `proptest` (about 20 crates). The inner UML sections with empty
lists, which would state an absence that is not proven.

**Limit.**
- Against the Python default, the verdict differs for 8 of 53 demo variants. Three rules on
  symbols read UNKNOWN. Three scans with a global script read complete here and UNKNOWN there
  (`script_global` imports: 269 of 628 records in the Studio UI). Two scans have fewer gaps.
  `test_collector_native_verdicts.py` lists them. PR 4.4 needs a decision on this.
- The UNKNOWN records of a construct rule and a catalog rule have another text, as the native
  scan declares no construct capability. The verdicts are equal.
- `serde_json` refuses `NaN` and a lone surrogate in a `package.json`. Python accepts both. The
  JSDoc `\w` follows Rust `char::is_alphanumeric`.
- A path without a module identity is an unresolved target. Python stops with an error.
- The build needs a C compiler. `cargo deny` needs an exception for `cc` at build time.
