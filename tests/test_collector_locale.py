# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-325: every collector process runs in the C locale, so all collectors give the same facts.

Consumer: the host process port (`analyzer/process.py`). The tree-sitter scanner calls the C
function `iswspace`. Its answer depends on the locale: after `const a = 1` and U+3000 at the
line end, the Python collector read the next line as a continuation under a UTF-8 locale. The
native collector never calls `setlocale`, so it always behaves like the C locale.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import decode_response, encode_request
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

SOURCE = "const a = 1\u3000\nconst b = 2\n"
PYTHON_COLLECTOR = (sys.executable, "-I", "-B", "-m", "archkeel.analyzer.typescript.entry")


def _utf8_locale() -> str | None:
    """Return a locale name that this machine has and whose `iswspace` knows U+3000."""
    for name in ("en_US.UTF-8", "C.UTF-8"):
        probe = subprocess.run(
            [sys.executable, "-I", "-c", "import locale; locale.setlocale(locale.LC_ALL, '')"],
            env={**os.environ, "LC_ALL": name},
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return name
    return None


def _tree(root: Path, source: str = SOURCE, name: str = "a.ts") -> None:
    (root / "src").mkdir()
    (root / "src" / name).write_text(source, encoding="utf-8")
    (root / "tsconfig.json").write_text("{}\n")


def _request(root: Path) -> CollectionRequest:
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(("src",), "app"),
        TypeScriptSettings("tsconfig.json"),
        ProtocolVersion.V3,
    )


def _oracle(root: Path, locale_name: str) -> SourceFacts:
    """Run the collector entry directly, so that `locale_name` is the only locale it gets.

    This path skips `ProcessCollector`, so it does not depend on the value that the host pins.
    """
    environment = {key: value for key, value in os.environ.items() if not key.startswith("LC_")}
    environment.pop("LANG", None)
    environment["LC_ALL"] = locale_name
    done = subprocess.run(
        PYTHON_COLLECTOR,
        input=encode_request(_request(root)),
        cwd=root,
        env=environment,
        capture_output=True,
        check=True,
    )
    return decode_response(done.stdout).facts


def _facts(root: Path, argv: tuple[str, ...], parent_locale: dict[str, str]) -> SourceFacts:
    parent = {key: value for key, value in os.environ.items() if not key.startswith("LC_")}
    parent.pop("LANG", None)
    parent.update(parent_locale)
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(parent)
    try:
        response = ProcessCollector(argv).collect_response(_request(root))
    finally:
        os.environ.clear()
        os.environ.update(saved)
    assert isinstance(response, CollectionResponse), response
    return response.facts


def test_the_child_environment_pins_the_c_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}
    real = subprocess.Popen

    def spy(*args: object, **options: object) -> subprocess.Popen[bytes]:
        seen.update(options["env"])  # type: ignore[call-overload]
        return real(*args, **options)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "Popen", spy)
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    monkeypatch.setenv("LC_CTYPE", "fr_FR.UTF-8")
    code = "import sys; sys.stdout.write(sys.stdin.read())"
    ProcessCollector((sys.executable, "-B", "-c", code)).collect(_request(Path.cwd()))

    assert seen["LC_ALL"] == "C"
    assert seen["PYTHONDONTWRITEBYTECODE"] == "1"
    # `LC_ALL` has precedence over `LANG` and `LC_CTYPE`, so these values change nothing.
    assert seen["LANG"] == "de_DE.UTF-8"


@pytest.mark.skipif(os.name == "nt", reason="Windows has no LC_ALL: the C library ignores it.")
def test_python_collector_gives_the_same_facts_under_any_user_locale(tmp_path: Path) -> None:
    name = _utf8_locale()
    if name is None:
        pytest.skip("this machine has no UTF-8 locale")
    _tree(tmp_path)

    pinned = _facts(tmp_path, PYTHON_COLLECTOR, {"LC_ALL": "C"})
    user = _facts(tmp_path, PYTHON_COLLECTOR, {"LC_ALL": name, "LANG": name})
    plain = _facts(tmp_path, PYTHON_COLLECTOR, {"LANG": name})

    assert user == pinned
    assert plain == pinned
    assert len(pinned.files) == 1


@pytest.mark.skipif(os.name == "nt", reason="Windows has no LC_ALL: the C library ignores it.")
@pytest.mark.parametrize("space", ["　", " ", " ", " ", " "])
def test_a_non_ascii_space_before_a_newline_reads_like_the_c_locale(
    tmp_path: Path, space: str
) -> None:
    name = _utf8_locale()
    if name is None:
        pytest.skip("this machine has no UTF-8 locale")
    _tree(tmp_path, f"const a = 1{space}\nconst b = 2\n")

    pinned = _facts(tmp_path, PYTHON_COLLECTOR, {"LC_ALL": "C"})
    user = _facts(tmp_path, PYTHON_COLLECTOR, {"LC_ALL": name})

    assert user == pinned


@pytest.mark.skipif(os.name == "nt", reason="Windows has no LC_ALL: the C library ignores it.")
def test_a_non_ascii_file_name_and_text_keep_their_path_and_facts(tmp_path: Path) -> None:
    name = _utf8_locale()
    if name is None:
        pytest.skip("this machine has no UTF-8 locale")
    _tree(tmp_path, "export const größe = 'Straße';\nexport const b = 2;\n", "grüße-é.ts")

    pinned = _facts(tmp_path, PYTHON_COLLECTOR, {"LC_ALL": "C"})
    user = _facts(tmp_path, PYTHON_COLLECTOR, {"LC_ALL": name})

    assert user == pinned
    assert [item.rel_path for item in pinned.files] == ["src/grüße-é.ts"]


@pytest.mark.skipif(os.name == "nt", reason="Windows has no LC_ALL: the C library ignores it.")
@pytest.mark.parametrize(("space", "differs"), [("\u3000", True), ("\u00a0", False)])
def test_the_host_gives_the_facts_of_the_c_locale_under_a_utf8_parent(
    tmp_path: Path, space: str, differs: bool
) -> None:
    name = _utf8_locale()
    if name is None:
        pytest.skip("this machine has no UTF-8 locale")
    _tree(tmp_path, f"const a = 1{space}\nconst b = 2\n")
    expected = _oracle(tmp_path, "C")

    if differs:
        # The oracle must show the divergence on this machine, or the test would prove nothing.
        assert _oracle(tmp_path, name) != expected
    assert _facts(tmp_path, PYTHON_COLLECTOR, {"LC_ALL": name}) == expected
    assert _facts(tmp_path, PYTHON_COLLECTOR, {"LANG": name}) == expected
