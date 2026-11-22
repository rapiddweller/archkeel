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
from test_cli_native_python_imports import RULE as RULE_HEAD
from test_cli_native_python_imports import component, project, verdict

from archkeel.cli.core_arguments import Options
from archkeel.cli.core_binding import ProjectRoot
from archkeel.cli.core_frame import CoreCommand
from archkeel.cli.core_only import _exchange_scan
from archkeel.explorer_queries import populate, query
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot
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
        # AD-1058: the lazy `getattr(module, key)` keeps its trojan horse site, so the module
        # keeps no proven key and the run is UNKNOWN until a contract declares the site.
        assert frame["status"] == "UNKNOWN", frame
        kinds = {gap["reason"] for gap in frame["collection_gaps"]}
        assert kinds == {"dynamic_import: getattr"}, kinds


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


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("return True", "PASS"),
        ("return purge(None)", "FAIL"),
        ("return callback(None)", "UNKNOWN"),
        ("def inner(): return purge(None)\n    return inner()", "UNKNOWN"),
    ],
)
def test_call_owner_selects_a_function_body(release_core: Path, body: str, expected: str) -> None:
    with fixture_tree(DEMO) as root:
        _policy(root, source="sample.report.run")
        (root / "sample/report.py").write_text(
            "from sample.maintenance import purge\n\ndef run(callback=None):\n    " + body + "\n",
            encoding="utf-8",
        )
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"].get(RULE) == ["call_owner", expected], frame


def test_function_scope_requires_the_selected_body_and_target(release_core: Path) -> None:
    with fixture_tree(DEMO) as root:
        _policy(root, source="sample.report.absent")
        frame = verdict(release_core, root, "report")["frame"]
        assert frame["status"] == "UNKNOWN" and RULE in frame["unsupported"]["rules"], frame
        _policy(root, source="sample.report.summarize", target="sample.maintenance.absent")
        frame = verdict(release_core, root, "report")["frame"]
        assert frame["rules"].get(RULE) == ["call_owner", "UNKNOWN"], frame


def test_function_scope_ignores_calls_in_other_bodies(release_core: Path) -> None:
    with fixture_tree(DEMO) as root:
        _policy(root, source="sample.report.run")
        (root / "sample/report.py").write_text(
            "def other(callback): return callback()\n\ndef run(): return True\n", encoding="utf-8"
        )
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"].get(RULE) == ["call_owner", "PASS"], frame


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
                **RULE_HEAD,
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
    frame = verdict(release_core, root)["frame"]
    if expected == "UNKNOWN":
        assert frame["status"] == "UNKNOWN" and "OWN-PAGE" in frame["unsupported"]["rules"], frame
    else:
        assert frame["rules"]["OWN-PAGE"] == ["call_owner", expected]


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


def test_explorer_links_function_constructor_and_proved_receiver_declarations(
    release_core: Path, tmp_path: Path
) -> None:
    provider = STORE + "\ndef load(): return Store()\n"
    caller = (
        "from app.service import Store, load\n"
        "from app import service\n"
        "def direct(): return load()\n"
        "def constructed(): return Store()\n"
        "def fresh(): return Store().page()\n"
        "def unknown(receiver): return receiver.page()\n"
        "def qualified(): return service.load()\n"
        "def shadowed(service): return service.load()\n"
    )
    root = call_owner_project(tmp_path, provider, caller, "app.service.Store.page")
    project_root = ProjectRoot.of(root, None)
    document = json.loads(
        _exchange_scan(
            Options(
                command=CoreCommand.REPORT, config=project_root.config, topology=True, explorer=True
            ),
            project_root,
            release_core,
            [],
        )[0]
    )
    assert document["rules"]["OWN-PAGE"] == ["call_owner", "FAIL"]
    topology = dict(
        document["topology"], explorer=document["explorer"], locations=document["locations"]
    )
    snapshot = tmp_path / "cache" / "explorer.sqlite"
    publish_snapshot(
        snapshot,
        SnapshotIdentity("rev", "contract", "source"),
        lambda db: populate(db, topology, root),
        "complete",
    )
    part = document["explorer"][0]
    for caller_name, expression, target_name, site_line, declaration_line in [
        ("direct", "load", "load", 3, 5),
        ("constructed", "Store", "Store", 4, 1),
        ("fresh", "Store().page", "Store.page", 5, 2),
    ]:
        (source,) = query(snapshot, root, "search", {"text": f"app.client.{caller_name}"})["items"]
        (call,) = [
            row
            for row in query(
                snapshot,
                root,
                "relations",
                {"element": source["id"], "direction": "out", "kind": "call"},
            )["items"]
            if row["expression"] == expression
        ]
        result = query(snapshot, root, "evidence", {"relation": call["id"]})
        assert result["relation"]["resolution"] == "resolved"
        assert result["relation"]["target_name"] == f"app.service.{target_name}"
        assert [(loc["role"], loc["path"], loc["line"]) for loc in result["items"]] == [
            ("call_site", "src/app/client.py", site_line),
            ("declaration", "src/app/service.py", declaration_line),
        ]
        assert (
            query(snapshot, root, "source", {"reference": result["items"][1]["reference"]})["line"]
            == declaration_line
        )

    for expression in ("receiver.page", "service.load"):
        rows = [row for row in part["calls"] if row["expression"] == expression]
        assert rows and all(row["status"] == "unresolved" for row in rows)
    assert [
        (row["target"], document["locations"][row["call_evidence"]]["line"])
        for row in part["source_call_candidates"]
        if row["expression"] == "service.load"
    ] == [("app.service.load", 7)]
