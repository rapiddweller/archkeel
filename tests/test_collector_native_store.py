# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-346: the reply of a TypeScript collector through the Rust store, against the Python path.

Consumer: the host (`run_report`) with `ARCHKEEL_NATIVE_STORE`. The store validates the reply,
the Python check reads the read-set, and the store writes `architecture.json`. On each golden case
the bytes of `architecture.json` and the verdicts must equal the Python path, for the native
collector and for the Python collector. The false-PASS probes run on the store path too.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import false_pass_support as support
import pytest
from conftest import build_native_copy
from filelock import FileLock

from archkeel.analyzer.process import ProcessCollector
from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import NATIVE_STORE, observer_for
from archkeel.ir.codec import canonical_report_bytes
from archkeel.ir.store_seam import active_store, close_store
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import repository
from tools import python_printable

ROOT = Path(__file__).parents[1]
CASES = json.loads((ROOT / "tests/golden/typescript/cases.json").read_text(encoding="utf-8"))
NAME = "archkeel-store.exe" if sys.platform == "win32" else "archkeel-store"
# The rule families of the full false-PASS probes (`test_collector_false_pass_full.py`).
FAMILIES = {
    "interfaces-and-exports": "typescript-module-interface",
    "layering": "typescript-layer-order-positive",
}
BY_ID = {variant.id: variant for variant in VARIANTS}


@pytest.fixture(scope="session")
def store_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The debug store binary; the workspace build of `build_native_copy` builds it too."""
    build_native_copy(tmp_path_factory, "store-collector")
    copy = tmp_path_factory.mktemp("store") / NAME
    with FileLock(str(ROOT / "native/target/.pytest-native-build.lock")):
        shutil.copy2(ROOT / "native/target/debug" / NAME, copy)
    return copy


@pytest.fixture(autouse=True)
def no_session_left() -> Iterator[None]:
    yield
    close_store()


def _repository(source: Path, workspace: Path) -> Path:
    root = workspace / "repo"
    shutil.copytree(source, root, ignore=shutil.ignore_patterns("node_modules", ".git"))
    if (root / "resolver-inputs").is_dir():
        shutil.copytree(root / "resolver-inputs", root / "node_modules")
    for command in (
        ["init", "-q"],
        ["add", "-A", "--force"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c"],
    ):
        subprocess.run(["git", *command], cwd=root, check=True, capture_output=True)
    return root


def _run(
    root: Path, argv: tuple[str, ...] | None, store: Path | None, monkeypatch: pytest.MonkeyPatch
) -> tuple[bytes | None, dict[str, Any]]:
    if store is None:
        monkeypatch.delenv(NATIVE_STORE, raising=False)
    else:
        monkeypatch.setenv(NATIVE_STORE, str(store))
    config = load_config(root)
    observer = observer_for(
        config.language, collector_argv=argv, tsconfig=config.tsconfig or "tsconfig.json"
    )
    assert isinstance(observer.collector, ProcessCollector)
    assert (observer.collector.store is not None) is (store is not None)
    result, artifact = run_report(root, config=config, analyzer=observer)
    close_store()
    return artifact, {
        "rules": {item.id: str(item.status) for item in result.rule_assessments or ()},
        "complete": str(result.observation_complete.value),
        "exit": result.exit_code,
        "diagnostics": sorted(
            (str(item.kind.value), item.subject, item.unknown_claim) for item in result.diagnostics
        ),
    }


@pytest.mark.parametrize("case", CASES, ids=[case["case"] for case in CASES])
def test_the_store_path_writes_the_bytes_and_verdicts_of_the_python_path(
    tmp_path: Path,
    native_binary: Path,
    store_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, str],
) -> None:
    root = _repository(ROOT / case["root"], tmp_path)
    for argv in ((str(native_binary),), None):
        python_bytes, python_verdict = _run(root, argv, None, monkeypatch)
        store_bytes, store_verdict = _run(root, argv, store_binary, monkeypatch)
        label = (case["case"], "native" if argv else "python collector")
        assert store_verdict == python_verdict, label
        assert python_bytes is not None, label
        assert store_bytes == python_bytes, label


def test_the_python_writer_refuses_an_observation_that_the_store_holds(
    tmp_path: Path, store_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(ROOT / "fixtures/H-typescript", tmp_path)
    monkeypatch.setenv(NATIVE_STORE, str(store_binary))
    config = load_config(root)
    observer = observer_for(config.language, tsconfig=config.tsconfig or "tsconfig.json")
    from archkeel.check.report import run_report_with_observation

    _, _, observation = run_report_with_observation(root, config=config, analyzer=observer)
    assert observation is not None and active_store() is not None
    with pytest.raises(ValueError, match="the Rust store writes this observation"):
        canonical_report_bytes(observation)


@pytest.fixture(scope="module")
def probe_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return support.copy_repository(ROOT / "fixtures/H-typescript", tmp_path_factory.mktemp("probe"))


@pytest.mark.parametrize(("tamper", "argument"), support.probe_params(support.TYPESCRIPT))
def test_a_changed_typescript_reply_gives_no_pass_on_the_store_path(
    probe_root: Path,
    store_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
    argument: str,
) -> None:
    monkeypatch.setenv(NATIVE_STORE, str(store_binary))
    support.assert_not_pass(probe_root, "typescript", tamper, argument)


def test_the_store_refuses_a_feature_whose_proof_it_does_not_check(
    tmp_path: Path, store_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(ROOT / "fixtures/H-typescript", tmp_path)
    script = tmp_path / "claim.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT / 'tests')!r})\n"
        "import false_pass_support as support\n"
        "reply, compressed = support._reply('typescript')\n"
        "reply['facts']['capabilities']['resolution_features'].append('call-bindings-v1')\n"
        "support.send(reply, compressed)\n",
        encoding="utf-8",
    )
    _, verdict = _run(root, (sys.executable, "-I", "-B", str(script)), store_binary, monkeypatch)
    assert verdict["complete"] != "PASS" and verdict["exit"] != 0
    claims = [item[2] for item in verdict["diagnostics"]]
    assert any("does not check the resolution feature" in claim for claim in claims), claims


def test_the_store_refuses_property_members_whose_proof_it_does_not_check(
    tmp_path: Path, store_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Python check refuses `property_members` that disagree with the method proofs."""
    root = _repository(ROOT / "fixtures/H-typescript", tmp_path)
    script = tmp_path / "property.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT / 'tests')!r})\n"
        "import false_pass_support as support\n"
        "reply, compressed = support._reply('typescript')\n"
        "symbols = next(s for s in reply['facts']['sections'] if s['name'] == 'symbols')\n"
        "target = next(r for r in symbols['records'] if r['kind'] == 'class')\n"
        "target['data']['property_members'] = ['x']\n"
        "support.send(reply, compressed)\n",
        encoding="utf-8",
    )
    _, verdict = _run(root, (sys.executable, "-I", "-B", str(script)), store_binary, monkeypatch)
    assert verdict["complete"] != "PASS" and verdict["exit"] != 0
    claims = [item[2] for item in verdict["diagnostics"]]
    assert any("property_members" in claim for claim in claims), claims


@pytest.fixture(scope="module", params=sorted(FAMILIES))
def family_root(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    variant = BY_ID[FAMILIES[request.param]]
    return repository(tmp_path_factory.mktemp(request.param), variant)


@pytest.mark.parametrize(("tamper", "argument"), support.probe_params(support.TYPESCRIPT))
def test_a_changed_reply_gives_no_pass_for_each_rule_family_on_the_store_path(
    family_root: Path,
    store_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
    argument: str,
) -> None:
    # The rule families of `test_collector_false_pass_full.py`, on the store path.
    monkeypatch.setenv(NATIVE_STORE, str(store_binary))
    support.assert_not_pass(family_root, "typescript", tamper, argument)


@pytest.mark.parametrize("index", range(len(VARIANTS)))
def test_the_store_path_gives_the_verdicts_of_the_python_path_on_each_demo_variant(
    tmp_path: Path,
    native_binary: Path,
    store_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    index: int,
) -> None:
    # Each rule family of the demo catalog reads its fields from the read-set on the store path.
    root = repository(tmp_path, VARIANTS[index])
    for argv in ((str(native_binary),), None):
        python_bytes, python_verdict = _run(root, argv, None, monkeypatch)
        store_bytes, store_verdict = _run(root, argv, store_binary, monkeypatch)
        assert store_verdict == python_verdict, (VARIANTS[index].id, argv)
        assert store_bytes == python_bytes, (VARIANTS[index].id, argv)


def test_the_printable_table_of_the_store_is_the_table_of_this_python() -> None:
    # The receipt digest hashes Python `repr`, whose escapes follow the Unicode version.
    source = python_printable.OUTPUT.read_text(encoding="utf-8")
    version = re.search(r'UNICODE_VERSION: &str = "([0-9.]+)"', source)
    assert version is not None
    if version.group(1) != unicodedata.unidata_version:
        pytest.skip(f"the table is for Unicode {version.group(1)}")
    assert python_printable.main(["--check"]) == 0


def _check_verdict(workspace: Path) -> dict[str, Any]:
    from fixtures.reproduce_typescript import check_revisions

    workspace.mkdir()
    checked = check_revisions(workspace, workspace)
    dimensions = checked["delta"]["dimensions"]
    return {
        "exit": checked["exit_code"],
        "complete": checked["observation_complete"],
        "expectation": checked["expectation_fulfilled"],
        "dimensions": {name: item["status"] for name, item in dimensions.items()},
    }


def test_check_with_the_store_set_gives_the_verdict_of_check_without_it(
    tmp_path: Path, store_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `check` hashes two observations with the Python writer, so it runs without the store.
    monkeypatch.delenv(NATIVE_STORE, raising=False)
    plain = _check_verdict(tmp_path / "plain")
    monkeypatch.setenv(NATIVE_STORE, str(store_binary))
    assert _check_verdict(tmp_path / "store") == plain
