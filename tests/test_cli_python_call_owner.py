# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The call-owner rule uses a proved target, not a call candidate."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from core_support import ROOT
from test_cli_native_python_imports import verdict

from tools.fixture_tree import fixture_tree

DEMO = ROOT / "fixtures/python-newer-syntax-demo"
RULE = "CALL-PURGE-MAINTENANCE-ONLY"


def _policy(root: Path, **changes: str) -> None:
    path = root / "docs/architecture/architecture-contract.json"
    contract = json.loads(path.read_bytes())
    rule = next(rule for rule in contract["rules"] if rule["id"] == RULE)
    rule.update(changes)
    path.write_text(json.dumps(contract), encoding="utf-8")


def _no_legacy_call(root: Path) -> None:
    path = root / "sample/legacy.py"
    path.write_bytes(
        path.read_bytes().replace(b"handle.close()  # type: ignore[attr-defined]", b"return None")
    )


def _python(root: Path, script: str) -> None:
    subprocess.run([sys.executable, "-B", "-c", script], cwd=root, check=True)


def test_nested_generator_keeps_the_forbidden_call_beside_open_calls(release_core: Path) -> None:
    result = verdict(release_core, DEMO, "report")
    frame = result["frame"]
    assert frame["rules"].get(RULE) == ["call_owner", "FAIL"], frame["gaps"]
    assert frame["rules"]["CONSTRUCT-EXACT-TYPE-IGNORE"] == ["forbidden_construct", "PASS"]
    assert frame["measures"]["unresolved_attribute"] == 1
    [detail] = frame["details"][RULE]
    assert detail["target"] == "sample.maintenance.purge"
    assert {"path": "sample/report.py", "line": 9} in [
        frame["locations"][site] for site in detail["evidence"]
    ]
    assert result["exit_code"] == 1


@pytest.mark.parametrize("case", ["allowed", "callback", "provider"])
def test_call_owner_distinguishes_allowed_and_open_origins(release_core: Path, case: str) -> None:
    with fixture_tree(DEMO) as root:
        provider = root / "sample/maintenance.py"
        with provider.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n\ndef readable(cell): return True\n"
                "\n\ndef purge_owned(cell): return purge(cell)\n"
            )
        if case == "provider":
            (root / "sample/__init__.py").write_text(
                "from importlib import import_module\n"
                'key = "sample.maintenance"\n'
                'provider = import_module(key + "")\n'
                "provider.purge = lambda cell: False\n",
                encoding="utf-8",
            )
            witness = "assert m.purge.__name__ == '<lambda>'; assert summarize([[None]]) == [False]"
        else:
            _no_legacy_call(root)
            if case == "allowed":
                source = (
                    "from sample.maintenance import readable\n"
                    "def summarize(rows):\n"
                    "    return [[readable(cell) for cell in row] for row in rows]\n"
                )
                witness = "assert summarize([[None]]) == [[True]]; assert m.purge_owned(None)"
            else:
                source = "def summarize(rows, purge): return [purge(row[0]) for row in rows]\n"
                witness = (
                    "assert summarize([[1]], m.purge) == [False]; "
                    "assert summarize([[1]], m.readable) == [True]"
                )
            (root / "sample/report.py").write_text(source, encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "from sample import maintenance as m; from sample.report import summarize; "
                + witness,
            ],
            cwd=root,
            check=True,
        )
        frame = verdict(release_core, root, "report")["frame"]
    expected = "PASS" if case == "allowed" else "UNKNOWN"
    assert frame["rules"].get(RULE) == ["call_owner", expected], frame["gaps"]
    assert not frame["violations"].get(RULE)


@pytest.mark.parametrize("with_rule", [True, False])
def test_lazy_import_candidate_is_not_a_live_import_witness(
    release_core: Path, with_rule: bool
) -> None:
    with fixture_tree(DEMO) as root:
        _no_legacy_call(root)
        (root / "sample/__init__.py").write_text(
            "from importlib import import_module\n"
            "from warnings import warn\n"
            "_table = {'sub': (__spec__.parent, '__module__'),\n"
            "          'purge': (__spec__.parent, '.maintenance'),\n"
            "          'Beta': (__spec__.parent, '.second'),\n"
            "          'Old': (__spec__.parent, '.maintenance')}\n"
            "_old = {'Old'}\n"
            "def _migrate(name):\n"
            "    raise AttributeError(name)\n"
            "def __getattr__(attr_name):\n"
            "    if attr_name in _old:\n"
            "        warn('old', stacklevel=2)\n"
            "    entry = _table.get(attr_name)\n"
            "    if entry is None:\n"
            "        return _migrate(attr_name)\n"
            "    package, module_name = entry\n"
            "    if module_name == '__module__':\n"
            "        result = import_module(f'.{attr_name}', package=package)\n"
            "        globals()[attr_name] = result\n"
            "        return result\n"
            "    else:\n"
            "        module = import_module(module_name, package=package)\n"
            "        result = getattr(module, attr_name)\n"
            "        g = globals()\n"
            "        for k, (_, other) in _table.items():\n"
            "            if other == module_name and k not in _old:\n"
            "                g[k] = getattr(module, k)\n"
            "        return result\n",
            encoding="utf-8",
        )
        (root / "sample/second.py").write_text("Beta = 3\n", encoding="utf-8")
        (root / "sample/sub.py").write_text("x = 1\n", encoding="utf-8")
        with (root / "sample/maintenance.py").open("a", encoding="utf-8") as stream:
            stream.write("\nOld = 2\n")
        (root / "sample/report.py").write_text(
            "from sample import purge\n\ndef run(): return purge(None)\n", encoding="utf-8"
        )
        if not with_rule:
            path = root / "docs/architecture/architecture-contract.json"
            contract = json.loads(path.read_bytes())
            contract["rules"] = [rule for rule in contract["rules"] if rule["id"] != RULE]
            path.write_text(json.dumps(contract), encoding="utf-8")
        _python(root, "from sample.report import run; assert run() is True")
        frame = verdict(release_core, root, "report")["frame"]
    if with_rule:
        assert frame["rules"].get(RULE) == ["call_owner", "UNKNOWN"], frame
    else:
        assert frame["status"] == "PASS", frame
    assert frame["measures"]["calls_resolved"] >= 1


@pytest.mark.parametrize("caller", ["parent", "selected"])
def test_call_owner_selects_the_module_not_a_same_named_function(
    release_core: Path, caller: str
) -> None:
    with fixture_tree(DEMO) as root:
        _no_legacy_call(root)
        policy_source = "sample.report.leaf"
        _policy(root, source=policy_source)
        report = root / "sample/report"
        report.mkdir()
        (root / "sample/report.py").rename(report / "__init__.py")
        call = "from sample.maintenance import purge\n\ndef leaf(): return purge(None)\n"
        quiet = "def leaf(): return True\n"
        (report / "__init__.py").write_text(call if caller == "parent" else quiet, encoding="utf-8")
        (report / "leaf.py").write_text(call if caller == "selected" else quiet, encoding="utf-8")
        source = "sample.report" if caller == "parent" else policy_source
        _python(root, f"from {source} import leaf; assert leaf() is True")
        frame = verdict(release_core, root, "report")["frame"]
    expected = "PASS" if caller == "parent" else "FAIL"
    assert frame["rules"].get(RULE) == ["call_owner", expected], frame
    if caller == "selected":
        [detail] = frame["details"][RULE]
        assert {"path": "sample/report/leaf.py", "line": 3} in [
            frame["locations"][site] for site in detail["evidence"]
        ]


@pytest.mark.parametrize(("expression", "calls"), [("purge", 1), ("factory()", 2)])
def test_decorator_application_counts_as_an_open_call(
    release_core: Path, expression: str, calls: int
) -> None:
    with fixture_tree(DEMO) as root:
        _no_legacy_call(root)
        _policy(root, source="sample.report")
        (root / "sample/maintenance.py").write_text(
            "def purge(fn): return 'decorated'\n\ndef factory(): return purge\n",
            encoding="utf-8",
        )
        (root / "sample/report.py").write_text(
            f"from sample.maintenance import purge, factory\n\n@{expression}\ndef run(): pass\n",
            encoding="utf-8",
        )
        _python(root, "from sample.report import run; assert run == 'decorated'")
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"].get(RULE) == ["call_owner", "UNKNOWN"], frame
    assert frame["measures"]["calls_total"] == calls
