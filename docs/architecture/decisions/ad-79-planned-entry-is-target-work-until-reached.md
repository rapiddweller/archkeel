# AD-79 A planned entry is target work until code reaches it

A built but unreached planned entry remains target work. Imports or declared facade signatures
reaching it require promotion to public. An exact planned module counts as a boundary-rule subject
without becoming an observed public interface.

An exact same-component planned-to-public move narrows under `--against`; other additions/removals
retain normal fail-closed classification. Proof:
[test_validation.py](../../../tests/test_validation.py) and
[test_widening.py](../../../tests/test_widening.py).
