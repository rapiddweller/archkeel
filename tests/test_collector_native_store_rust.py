# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-346: Rust replies and test exclusion (protocol 9) through the Rust store.

Consumer: the host (`run_report`, `run_explore`) with `ARCHKEEL_NATIVE_STORE`. On the store path
the bytes of `architecture.json` and the verdicts must equal the Python path. A changed Rust reply
gives no PASS on either path. Explore observes twice with one collection, so its second pass must
keep the store of the first.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import false_pass_support as support
import pytest
from collector_pin import pin_of
from graph_report_support import commit_tree
from rust_repository import CRATE_RULES, repository, rule
from test_collector_false_pass_full import MODULE_FILES, MODULE_LIB

from archkeel.analyzer import store
from archkeel.check.report import run_explore, run_report, run_report_with_observation
from archkeel.cli.config import load_config
from archkeel.cli.observe import NATIVE_STORE, observer_for
from archkeel.ir.languages import Language
from archkeel.ir.store_seam import active_store, close_store

ROOT = Path(__file__).parents[1]
# Each case is a set of files over the default fixture of `rust_repository`.
TESTS = {
    "crates/app/tests/it.rs": "use base_crate::make;\n#[test]\nfn t() { make(); }\n",
    "crates/app/src/lib.rs": (
        "use base_crate::make;\npub fn run() { make(); }\n"
        "#[cfg(test)]\nmod tests { use std::fmt; fn t() { let _ = fmt::Error; } }\n"
    ),
}
MODULES = {
    "crates/app/src/lib.rs": MODULE_LIB,
    **MODULE_FILES,
    "crates/app/src/a.rs": "use crate::b::make;\npub fn run() { make(); std::mem::drop(1); }\n",
    "crates/base/src/lib.rs": "pub fn make() {}\npub mod inner { pub fn deep() {} }\n",
}
CASES = {"crates": {}, "tests": TESTS, "modules": MODULES}
FORBIDDEN = rule(
    "NO-A-TO-C",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.c",
    include_type_checking=True,
)


def _count_sessions(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The store binaries that a run opens a session of, so a test sees that the store ran."""
    opened: list[str] = []
    original = store.StoreSession.__init__

    def counted(self: store.StoreSession, binary: str, *args: int) -> None:
        opened.append(Path(binary).name)
        original(self, binary, *args)

    monkeypatch.setattr(store.StoreSession, "__init__", counted)
    return opened


def _report(
    root: Path, binary: Path, store: Path | None, monkeypatch: pytest.MonkeyPatch
) -> tuple[bytes | None, dict[str, Any]]:
    if store is None:
        monkeypatch.delenv(NATIVE_STORE, raising=False)
    else:
        monkeypatch.setenv(NATIVE_STORE, str(store))
    config = load_config(root)
    # A pinned collector is trusted, so its rules can PASS (AD-344).
    observer = observer_for(
        config.language,
        collector_argv=(str(binary),),
        pinned_digest=pin_of(str(binary)),
        exclude_test_sources=config.exclude_test_sources,
    )
    opened = _count_sessions(monkeypatch)
    result, artifact = run_report(root, config=config, analyzer=observer)
    close_store()
    assert len(opened) == (store is not None)
    return artifact, {
        "rules": {item.id: str(item.status) for item in result.rule_assessments or ()},
        "complete": str(result.observation_complete.value),
        "exit": result.exit_code,
        "diagnostics": sorted(
            (str(item.kind.value), item.subject, item.unknown_claim) for item in result.diagnostics
        ),
    }


@pytest.mark.parametrize("exclude", [False, True], ids=["protocol 3", "protocol 9"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_the_store_path_writes_the_bytes_and_verdicts_of_the_python_path_for_rust(
    tmp_path: Path,
    rust_binary: Path,
    store_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    exclude: bool,
) -> None:
    rules = (*CRATE_RULES, FORBIDDEN) if case == "modules" else CRATE_RULES
    root = repository(tmp_path, rust_binary, CASES[case], rules=rules)
    if exclude:
        with (root / "archkeel.toml").open("a", encoding="utf-8") as file:
            file.write("exclude_test_sources = true\n")
        commit_tree(root)
    python_bytes, python_verdict = _report(root, rust_binary, None, monkeypatch)
    store_bytes, store_verdict = _report(root, rust_binary, store_binary, monkeypatch)
    assert python_verdict["complete"] == "PASS", python_verdict
    assert store_verdict == python_verdict
    assert python_bytes is not None
    assert store_bytes == python_bytes


@pytest.fixture(scope="module")
def probe_root(tmp_path_factory: pytest.TempPathFactory, rust_binary: Path) -> Path:
    return repository(tmp_path_factory.mktemp("probe"), rust_binary)


@pytest.mark.parametrize("store", [False, True], ids=["python path", "store path"])
@pytest.mark.parametrize(("tamper", "argument"), support.probe_params(support.RUST))
def test_a_changed_rust_reply_gives_no_pass(
    probe_root: Path,
    rust_binary: Path,
    store_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    store: bool,
    tamper: str,
    argument: str,
) -> None:
    monkeypatch.setenv(support.RUST_COLLECTOR, str(rust_binary))
    if store:
        monkeypatch.setenv(NATIVE_STORE, str(store_binary))
    else:
        monkeypatch.delenv(NATIVE_STORE, raising=False)
    support.assert_not_pass(probe_root, "rust", tamper, argument, base_argv=(str(rust_binary),))


def test_explore_keeps_the_store_of_its_first_pass_with_test_exclusion(
    tmp_path: Path, native_binary: Path, store_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Explore excludes test sources (protocol 9) and observes twice with one collection.
    root = support.copy_repository(ROOT / "fixtures/H-typescript", tmp_path)
    opened = _count_sessions(monkeypatch)
    artifacts = []
    for binary in (None, store_binary):
        if binary is None:
            monkeypatch.delenv(NATIVE_STORE, raising=False)
        else:
            monkeypatch.setenv(NATIVE_STORE, str(binary))
        observer = observer_for(Language.TYPESCRIPT, collector_argv=(str(native_binary),))
        _, artifact, _ = run_explore(
            root,
            observer=observer,
            source="src",
            namespace="shop",
            language=Language.TYPESCRIPT,
            tsconfig="tsconfig.json",
        )
        close_store()
        artifacts.append(artifact)
    assert opened == [store_binary.name]
    assert artifacts[0] is not None
    assert artifacts[1] == artifacts[0]


def test_a_failed_observation_closes_the_store_of_an_earlier_collection(
    tmp_path: Path, rust_binary: Path, store_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = repository(tmp_path / "good", rust_binary)
    bad = repository(tmp_path / "bad", rust_binary)
    (bad / "architecture-contract.json").write_text("{", encoding="utf-8")
    commit_tree(bad)
    monkeypatch.setenv(NATIVE_STORE, str(store_binary))
    for root in (good, bad):
        config = load_config(root)
        observer = observer_for(
            config.language,
            collector_argv=(str(rust_binary),),
            pinned_digest=pin_of(str(rust_binary)),
        )
        result, _, _ = run_report_with_observation(root, config=config, analyzer=observer)
        assert (active_store() is not None) is (root == good), result.diagnostics


def _report_files(
    root: Path,
    config: str | None,
    store: Path | None,
    rust: Path,
    out: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, bytes]:
    """`archkeel report --json`: the result document and the three files it writes."""
    import archkeel.cli as cli

    if store is None:
        monkeypatch.delenv(NATIVE_STORE, raising=False)
    else:
        monkeypatch.setenv(NATIVE_STORE, str(store))

    def pinned(language: Language, **options: Any) -> Any:
        if language is Language.RUST:
            options.update(collector_argv=(str(rust),), pinned_digest=pin_of(str(rust)))
        return observer_for(language, **options)

    monkeypatch.setattr(cli, "observer_for", pinned)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    argv = ["report", "--root", str(root), "--output", str(out / "architecture.json"), "--json"]
    capsys.readouterr()
    cli.main([*argv, *(["--config", config] if config else [])])
    close_store()
    files = {path.name: path.read_bytes() for path in sorted(out.iterdir())}
    return {"result": capsys.readouterr().out.encode(), **files}


@pytest.mark.parametrize(
    "repo",
    ["native tree", "rust fixture", "H-typescript", "H-uml-typescript", "F-typescript-story"],
)
def test_the_store_path_writes_the_result_and_the_pages_of_the_python_path(
    tmp_path: Path,
    rust_binary: Path,
    store_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    repo: str,
) -> None:
    # The whole result document and both pages, not only architecture.json and the verdicts: a
    # reader of the observation (the UML graph, the hubs, the cycles) sees every field it reads.
    config = None
    if repo == "native tree":
        root, config = ROOT, "native/archkeel.toml"
        monkeypatch.chdir(ROOT)
    elif repo == "rust fixture":
        root = repository(tmp_path / "repo", rust_binary, MODULES, rules=(*CRATE_RULES, FORBIDDEN))
    else:
        root = support.copy_repository(ROOT / "fixtures" / repo, tmp_path)
    out = tmp_path / "out"
    python = _report_files(root, config, None, rust_binary, out, monkeypatch, capsys)
    stored = _report_files(root, config, store_binary, rust_binary, out, monkeypatch, capsys)
    assert {"architecture.json", "architecture.report.html", "architecture.detail.html"} <= set(
        python
    )
    assert stored.keys() == python.keys()
    for name in python:
        assert stored[name] == python[name], name


def test_the_source_graph_refuses_a_symbol_without_its_qualified_name() -> None:
    # #949 item 3: a read-set that lacks a field that a reader needs must fail, not default.
    from archkeel.ir.facts import EvidenceClass, Record
    from archkeel.ir.facts_codec import freeze_data
    from archkeel.ir.source_graph import _symbol

    data = {"module": "native.app", "name": "run", "parent": "native.app"}
    record = Record(
        "SYM-1",
        EvidenceClass.FACT,
        "source",
        "function",
        "",
        (),
        (),
        (),
        (),
        (),
        freeze_data(data),
    )
    with pytest.raises(ValueError, match="qualified_name of SYM-1"):
        _symbol(record, "rust")
