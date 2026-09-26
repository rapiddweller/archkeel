# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A requires target must name a component at the contract level that declares it."""

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest
from test_analyzer import _component

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, run_validate
from archkeel.cli import main
from archkeel.ir.model import Diagnostic


def _component_at(
    label: str,
    package: str,
    *,
    requires: tuple[str, ...] = (),
    inside: str | None = None,
) -> dict[str, object]:
    component = _component(label, packages=[package])
    if requires:
        component["requires"] = [
            {"component": target, "rationale": "Uses this peer."} for target in requires
        ]
    if inside is not None:
        component["inside"] = inside
    return component


def _contract(
    components: list[dict[str, object]], *, complete_requires: bool = False
) -> dict[str, object]:
    rules = (
        [
            {
                "id": "REQUIRES-COMPLETE",
                "kind": "complete_requires",
                "rationale": "Every dependency pair is explicitly decided.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ]
        if complete_requires
        else []
    )
    return {"schema_version": "2.1.0", "components": components, "rules": rules}


def _write_repo(
    root: Path,
    *,
    app_requires: tuple[str, ...] = ("peer",),
    service_requires: tuple[str, ...] = ("local",),
    deep_requires: tuple[str, ...] = ("deep_peer",),
) -> ScanConfig:
    (root / "contracts").mkdir(parents=True, exist_ok=True)
    (root / "docs/architecture").mkdir(parents=True, exist_ok=True)
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "contract.json"\n',
        encoding="utf-8",
    )
    (root / "contract.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at(
                        "app", "sample.app", requires=app_requires, inside="contracts/one.json"
                    ),
                    _component_at("peer", "sample.peer", inside="contracts/peer.json"),
                ],
                complete_requires=True,
            )
        ),
        encoding="utf-8",
    )
    (root / "contracts/one.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at(
                        "service",
                        "sample.app.service",
                        requires=service_requires,
                        inside="contracts/two.json",
                    ),
                    _component_at("local", "sample.app.local"),
                ]
            )
        ),
        encoding="utf-8",
    )
    (root / "contracts/two.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at("deep", "sample.app.service.deep", requires=deep_requires),
                    _component_at("deep_peer", "sample.app.service.deep_peer"),
                ]
            )
        ),
        encoding="utf-8",
    )
    (root / "contracts/peer.json").write_text(
        json.dumps(_contract([_component_at("peer_api", "sample.peer.api")])),
        encoding="utf-8",
    )
    (root / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n", encoding="utf-8"
    )
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    for package in (
        "sample",
        "sample/app",
        "sample/app/service",
        "sample/app/local",
        "sample/app/service/deep",
        "sample/app/service/deep_peer",
        "sample/peer",
        "sample/peer/api",
    ):
        directory = root / package
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").write_text("", encoding="utf-8")
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "qa@example.invalid"],
        ["git", "config", "user.name", "QA"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def _append_component(root: Path, contract_path: str, component: dict[str, object]) -> None:
    path = root / contract_path
    raw = json.loads(path.read_bytes())
    raw["components"].append(component)
    path.write_text(json.dumps(raw), encoding="utf-8")


def _assert_requires_diagnostic(
    diagnostics: Iterable[Diagnostic], *, target: str, pointer: str
) -> None:
    matches = [item for item in diagnostics if item.pointer == pointer]
    assert len(matches) == 1, diagnostics
    diagnostic = matches[0]
    assert target in diagnostic.subject or target in diagnostic.unknown_claim


@pytest.mark.parametrize(
    ("level", "target", "pointer"),
    [
        ("root", "typo", "/components/0/requires/0/component"),
        ("nested-ancestor", "app", "/components/0/inside/components/0/requires/0/component"),
        ("nested-other-mount", "peer", "/components/0/inside/components/0/requires/0/component"),
        (
            "deep-ancestor",
            "service",
            "/components/0/inside/components/0/inside/components/0/requires/0/component",
        ),
    ],
    ids=[
        "root-typo",
        "nested-ancestor-is-not-local",
        "other-mount-is-not-local",
        "deep-ancestor-is-not-local",
    ],
)
def test_unknown_requires_target_is_rejected_at_its_declaring_level(
    tmp_path: Path, level: str, target: str, pointer: str
) -> None:
    requirements = (
        {"app_requires": (target,)}
        if level == "root"
        else {"deep_requires": (target,)}
        if level == "deep-ancestor"
        else {"service_requires": (target,)}
    )
    config = _write_repo(tmp_path, **requirements)

    result, _ = run_validate(tmp_path, config, observe)

    assert result.exit_code == 2, result.diagnostics
    _assert_requires_diagnostic(result.diagnostics, target=target, pointer=pointer)


def test_same_level_requires_targets_pass_at_root_nested_and_deep_levels(tmp_path: Path) -> None:
    config = _write_repo(tmp_path)

    result, _ = run_validate(tmp_path, config, observe)

    assert result.exit_code == 0, result.diagnostics
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("contract_path", "pointer"),
    [
        ("contract.json", "/components/2/label"),
        (
            "contracts/two.json",
            "/components/0/inside/components/0/inside/components/2/label",
        ),
    ],
    ids=["root", "deep"],
)
def test_duplicate_component_labels_are_rejected_with_second_label_pointer(
    tmp_path: Path, contract_path: str, pointer: str
) -> None:
    config = _write_repo(tmp_path)
    package = "sample.other" if contract_path == "contract.json" else "sample.app.service.other"
    contract_file = tmp_path / contract_path
    original_contract = contract_file.read_bytes()
    label = json.loads(original_contract)["components"][0]["label"]
    package_path = tmp_path / package.replace(".", "/")
    package_path.mkdir(parents=True)
    (package_path / "__init__.py").write_text("", encoding="utf-8")
    _append_component(
        tmp_path,
        contract_path,
        {**_component_at(label, package), "id": "COMP-OTHER"},
    )
    subprocess.run(
        ["git", "add", contract_path, package.replace(".", "/")],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "duplicate label"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    result, _ = run_validate(tmp_path, config, observe)
    report, _ = run_report(tmp_path, config=config, analyzer=observe)
    observed = observe(
        tmp_path,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    contract_file.write_bytes(original_contract)
    historical, _ = run_validate(tmp_path, config, observe, against="HEAD")

    assert result.exit_code == 2, result.diagnostics
    assert [item.pointer for item in result.diagnostics] == [pointer]
    assert (report.exit_code, tuple(item.pointer for item in report.diagnostics)) == (2, (pointer,))
    assert tuple(item.pointer for item in observed.diagnostics) == (pointer,)
    assert (historical.exit_code, tuple(item.pointer for item in historical.diagnostics)) == (
        2,
        (pointer,),
    )


def test_duplicate_component_labels_are_valid_across_contract_levels_and_mounts(
    tmp_path: Path,
) -> None:
    config = _write_repo(
        tmp_path,
        app_requires=(),
        service_requires=(),
        deep_requires=(),
    )
    for contract_path in (
        "contract.json",
        "contracts/one.json",
        "contracts/two.json",
        "contracts/peer.json",
    ):
        path = tmp_path / contract_path
        raw = json.loads(path.read_bytes())
        raw["components"][0]["label"] = "shared"
        path.write_text(json.dumps(raw), encoding="utf-8")

    result, _ = run_validate(tmp_path, config, observe)

    assert result.exit_code == 0, result.diagnostics
    assert result.diagnostics == ()


def test_cli_validate_rejects_unknown_requires_without_writing_baseline_or_graph(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_repo(tmp_path, app_requires=("ghost",))
    page = tmp_path / "docs/architecture/sample.md"
    page.write_text(f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n  stale --> old\n```\n")
    original_page = page.read_bytes()
    baseline = tmp_path / "baseline.json"

    exit_code = main(
        [
            "validate",
            "--root",
            str(tmp_path),
            "--write-graph",
            "--baseline",
            str(baseline),
            "--write-baseline",
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    actual = (
        exit_code,
        tuple(item["pointer"] for item in result["diagnostics"]),
        result["artifact"],
        baseline.exists(),
        page.read_bytes() == original_page,
    )
    assert actual == (2, ("/components/0/requires/0/component",), None, False, True), result


@pytest.mark.parametrize(
    ("requirements", "pointer"),
    [
        ({"app_requires": ("ghost",)}, "/components/0/requires/0/component"),
        (
            {"service_requires": ("ghost",)},
            "/components/0/inside/components/0/requires/0/component",
        ),
        (
            {"deep_requires": ("ghost",)},
            "/components/0/inside/components/0/inside/components/0/requires/0/component",
        ),
    ],
    ids=["root", "nested", "deep"],
)
def test_report_and_historical_observation_reject_unknown_requires_targets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    requirements: dict[str, tuple[str, ...]],
    pointer: str,
) -> None:
    config = _write_repo(tmp_path, **requirements)

    report, _ = run_report(tmp_path, config=config, analyzer=observe)
    observed = observe(
        tmp_path,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    exit_code = main(["report", "--root", str(tmp_path), "--json"])
    cli_result = json.loads(capsys.readouterr().out)

    contract_file = tmp_path / (
        "contract.json"
        if "app_requires" in requirements
        else "contracts/one.json"
        if "service_requires" in requirements
        else "contracts/two.json"
    )
    contract = json.loads(contract_file.read_bytes())
    contract["components"][0]["requires"] = []
    contract_file.write_text(json.dumps(contract))
    historical_exit = main(["validate", "--root", str(tmp_path), "--against", "HEAD", "--json"])
    historical = json.loads(capsys.readouterr().out)

    actual = {
        "run_report": (report.exit_code, tuple(item.pointer for item in report.diagnostics)),
        "observe": tuple(item.pointer for item in observed.diagnostics),
        "historical": (
            historical_exit,
            tuple(item["pointer"] for item in historical["diagnostics"]),
        ),
        "cli_report": (
            exit_code,
            tuple(item["pointer"] for item in cli_result["diagnostics"]),
        ),
    }
    expected = {
        "run_report": (2, (pointer,)),
        "observe": (pointer,),
        "historical": (2, (pointer,)),
        "cli_report": (2, (pointer,)),
    }
    assert actual == expected, actual
