# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Acceptance for the first source-bound receiver slice of #613."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_cli_native_python_imports import RULE, component, project, verdict

STORE = "class Store:\n    def page(self):\n        return 'store'\n"
STORED = "def run():\n    store = Store()\n    return store.page()\n"
IMPORTED = "from app.service import Store\n\n" + STORED
AMBIGUOUS = """\
from app.service import Store

class Runner:
    def __init__(self, store: Store):
        self.store = store

    def run(self):
        return self.store.page()
"""
REASSIGNED = IMPORTED.replace("def run():", "def run(other):").replace(
    "    return store.page()", "    store = other\n    return store.page()"
)


def call_owner_project(
    root: Path, provider: str, caller: str, target: str, **scope: str | list[str]
) -> Path:
    root = project(
        root,
        {
            "src/app/__init__.py": "",
            "src/app/service.py": provider,
            "src/app/client.py": caller,
        },
        contract_rules=[
            {
                **RULE,
                "id": "OWN-PAGE",
                "kind": "call_owner",
                "source": "app",
                "target": target,
                "exact_sources": ["app.service"],
                **scope,
            },
        ],
    )
    contract = root / "architecture-contract.json"
    data = json.loads(contract.read_text())
    data["schema_version"] = "3.7.0"
    data["components"] = [component("app", ["app"])]
    contract.write_text(json.dumps(data))
    return root


@pytest.mark.parametrize(
    ("provider", "caller", "run"),
    [
        pytest.param(STORE + "\n" + STORED, "", "assert service.run() == 'store'", id="owner"),
        pytest.param(STORE, IMPORTED, "assert client.run() == 'store'", id="planted-caller"),
        pytest.param(
            STORE,
            AMBIGUOUS,
            "assert client.Runner(service.Store()).run() == 'store'\n"
            "assert client.Runner(Other()).run() == 'other'",
            id="injected-receiver",
        ),
        pytest.param(
            STORE, REASSIGNED, "assert client.run(Other()) == 'other'", id="reassigned-receiver"
        ),
    ],
)
def test_the_same_annotation_does_not_fix_the_runtime_receiver(
    tmp_path: Path, provider: str, caller: str, run: str
) -> None:
    root = call_owner_project(tmp_path, provider, caller, "app.service.Store.page")
    setup = (
        "from app import client, service\n"
        "class Other(service.Store):\n"
        "    def page(self):\n"
        "        return 'other'\n"
    )
    subprocess.run([sys.executable, "-c", setup + run], cwd=root / "src", check=True)


@pytest.mark.parametrize(
    ("provider", "caller", "expected"),
    [
        pytest.param(STORE + "\n" + STORED, "", "PASS", id="owner"),
        pytest.param(STORE, IMPORTED, "FAIL", id="planted-caller"),
        pytest.param(STORE, AMBIGUOUS, "UNKNOWN", id="injected-receiver"),
        pytest.param(
            STORE,
            IMPORTED + "\n" + AMBIGUOUS.removeprefix("from app.service import Store\n\n"),
            "FAIL",
            id="planted-caller-beside-unknown",
        ),
        pytest.param(STORE, REASSIGNED, "UNKNOWN", id="reassigned-receiver"),
    ],
)
def test_call_owner_distinguishes_exact_and_ambiguous_receivers(
    release_core: Path, tmp_path: Path, provider: str, caller: str, expected: str
) -> None:
    root = call_owner_project(tmp_path, provider, caller, "app.service.Store.page")
    result = verdict(release_core, root)
    frame = result["frame"]
    assert frame["rules"].get("OWN-PAGE") == ["call_owner", expected], frame["gaps"]
    if expected == "FAIL":
        [detail] = frame["details"]["OWN-PAGE"]
        assert (detail["source"], detail["target"]) == ("app.client.run", "app.service.Store.page")
        place = frame["locations"][detail["evidence"][0]]
        assert (place["path"], place["line"]) == ("src/app/client.py", 5)


@pytest.mark.parametrize(
    ("allowance", "expected"),
    [
        ({"allowed_sources": ["app.client"]}, "PASS"),
        ({"exact_sources": ["app.client"]}, "PASS"),
        ({"exact_sources": ["app.client.run"]}, "PASS"),
        ({"allowed_sources": ["app.client.run"]}, "PASS"),
        ({"allowed_sources": ["app.cli"]}, "FAIL"),
        ({"exact_sources": ["app"]}, "FAIL"),
        ({"source": "app.client.run", "exact_sources": ["app.client.runner"]}, "FAIL"),
        ({"source": "app.service"}, "PASS"),
        ({"source": "app.missing"}, "UNKNOWN"),
    ],
)
def test_call_owner_matches_lexical_prefixes_and_exact_callers(
    release_core: Path, tmp_path: Path, allowance: dict[str, str | list[str]], expected: str
) -> None:
    direct = "from app.service import Store as Local\n\ndef run():\n    return Local().page()\n"
    root = call_owner_project(tmp_path, STORE, direct, "app.service.Store.page", **allowance)
    assert verdict(release_core, root)["frame"]["rules"]["OWN-PAGE"] == ["call_owner", expected]


def test_a_proved_other_method_does_not_match_the_target(
    release_core: Path, tmp_path: Path
) -> None:
    provider = STORE + "\n" + STORE.replace("Store", "Other")
    caller = IMPORTED.replace("Store", "Other")
    root = call_owner_project(tmp_path, provider, caller, "app.service.Store.page")
    assert verdict(release_core, root)["frame"]["rules"]["OWN-PAGE"] == ["call_owner", "PASS"]


def test_a_reflective_write_withholds_call_identity(release_core: Path, tmp_path: Path) -> None:
    provider = STORE + "\ntype.__setattr__(Store, 'page', lambda self: 'replacement')\n"
    root = call_owner_project(tmp_path, provider, IMPORTED, "app.service.Store.page")
    result = verdict(release_core, root)
    assert result["status"] == "UNKNOWN", result["frame"]
    assert not result["frame"]["violations"].get("OWN-PAGE")
