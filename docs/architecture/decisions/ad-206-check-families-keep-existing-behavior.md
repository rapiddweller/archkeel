# AD-206 Check families keep existing behavior

Move diagnostic families into focused validation modules while retaining
`run_validate` and existing callable imports. Apply the same boundary to type
evaluation. Function behavior stays unchanged.

No registry, new interface or policy widening is needed; this is responsibility
placement within the existing check boundary.

[Validation implementation](../../../src/archkeel/check/validation/__init__.py) and
[behavior controls](../../../tests/test_validation.py).
