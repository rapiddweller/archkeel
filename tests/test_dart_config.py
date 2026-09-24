# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""`[scan] language` selects the analyzer profile, and absence keeps today's Python config.

The key is the only new configuration input the Dart profile needs, so it is held to the same
closed-shape rules as the other three: a value outside the two profiles is refused rather than
read as Python, and a toml that never names it must stay the identical config it was (same
digest, same `ScanConfig`), or every accepted `check` baseline would move for nothing.
"""

import hashlib

import pytest

from archkeel.check.ports import ScanConfig
from archkeel.cli.config import ConfigError, parse_config

_BASE = b'[scan]\nroots = ["lib"]\nnamespace = "app"\ncontract = "contract.json"\n'


def test_absent_language_is_python_and_the_same_config() -> None:
    config = parse_config(_BASE)
    assert config.language == "python"
    assert config == ScanConfig(("lib",), "app", "contract.json", hashlib.sha256(_BASE).hexdigest())
    assert config.digest == hashlib.sha256(_BASE).hexdigest()


@pytest.mark.parametrize("language", ["python", "dart"])
def test_language_selects_a_supported_profile(language: str) -> None:
    payload = _BASE + f'language = "{language}"\n'.encode()
    config = parse_config(payload)
    assert config.language == language
    assert config == ScanConfig(
        ("lib",),
        "app",
        "contract.json",
        hashlib.sha256(payload).hexdigest(),
        language=language,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "value",
    [b'"kotlin"', b'"Dart"', b'"dart "', b'""', b"1", b"true", b'["dart"]'],
)
def test_language_outside_the_profiles_is_rejected(value: bytes) -> None:
    with pytest.raises(ConfigError):
        parse_config(_BASE + b"language = " + value + b"\n")


def test_other_extra_keys_stay_rejected_beside_language() -> None:
    with pytest.raises(ConfigError):
        parse_config(_BASE + b'language = "dart"\nframework = "flutter"\n')


def test_namespace_error_no_longer_says_python() -> None:
    payload = b'[scan]\nroots = ["lib"]\nnamespace = "my-app"\ncontract = "contract.json"\n'
    with pytest.raises(ConfigError) as error:
        parse_config(payload + b'language = "dart"\n')
    assert "ASCII dotted namespace" in str(error.value)
    assert "Python" not in str(error.value)


def test_scan_config_defaults_to_python_and_accepts_dart() -> None:
    assert ScanConfig(("lib",), "app", "contract.json", "0" * 64).language == "python"
    dart = ScanConfig(("lib",), "app", "contract.json", "0" * 64, language="dart")
    assert dart.language == "dart"
