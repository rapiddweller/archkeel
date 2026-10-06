# AD-43 A candidate declares what it changed, not what the scanner counted or what every module already carries

Semantic delta excludes coverage counters and only the exact `from __future__ import annotations`
crossing. Keep source imports in the full observation and check coverage separately. Otherwise
boilerplate or scan counts can look like architecture changes, while hiding coverage would lose
trust evidence.

Checker identity and provenance remain comparison constraints. Proof:
[test_delta.py](../../../tests/test_delta.py) and
[test_delta_parity.py](../../../tests/test_delta_parity.py).
