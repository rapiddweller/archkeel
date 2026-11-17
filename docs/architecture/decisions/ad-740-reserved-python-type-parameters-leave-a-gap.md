# AD-740: Reserved Python type parameters leave a gap

## Decision

The Python collector refuses a type parameter named `__classdict__`.
This applies to generic classes, functions and type aliases.
The refusal gives the file, line and compiler error as a coverage gap.
Rules that need the unread scope cannot pass on its absence.

## Reason

CPython 3.12, 3.13 and 3.14 refuse these parameters at compilation.
The grammar alone accepts them. A tree is not proof that a file compiles.
Publishing facts for that tree would omit the required gap.

## Alternatives and limits

Do not keep the tree and publish its facts: this hides the compiler refusal.
This check covers one compiler rule. It does not prove compiler parity for all inputs.
Issue #1072 remains open for the unproved compiler paths.

## Verification

`native/python/src/parse_tests.rs` checks each fixture on the supported versions.
`tests/test_cli_native_python_imports.py` checks the file, line and UNKNOWN verdict.
