# AD-7 Determinism is measured, not assumed

Canonical observation JSON, report HTML and stdout must be reproducible from the same code,
contract, configuration and runtime inputs. Environment changes must not leak into those bytes; do
not normalize differences away in the check.

[test_determinism.py](../../../tests/test_determinism.py) exercises controlled environment changes.
One build probe does not prove determinism across platforms or Python versions.
