# AD-47 `init` breaks a tie between top-level packages with `pyproject.toml`'s `[project] name`, and with nothing else

Infer a Python source/namespace only from one unambiguous package or a unique normalized
wheel-project-name match. Do not guess test exclusions or build backends. Ambiguous, unreadable or
mismatched layouts require explicit `--source` and `--namespace`, exiting two otherwise.

This keeps onboarding convenient without silently scanning the wrong package. Proof:
[test_onboarding.py](../../../tests/test_onboarding.py).
