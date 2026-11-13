# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-420: release scan refusals bound parse work before any syntax tree exists."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock
from test_cli_native_core_scan import (
    HONEST,
    ROOT,
    built,
    case_root,
    diagnostics,
    install,
    report,
)

from archkeel.analyzer.runtime import package_version
from archkeel.cli import main, native_core, native_scan
from archkeel.cli.core_frame import CoreError, GapKind

__all__ = ["built", "install"]

PEAK_BOUND = 128 * 1024 * 1024


def test_the_printed_core_error_uses_its_typed_gap() -> None:
    from archkeel.cli.core_frame import Gap

    error = CoreError("untyped message", gap=Gap(GapKind.PARSE_WORK_LIMIT, "source", "too deep"))
    assert "parse_work_limit" in str(error)
    assert "source" in str(error)
    assert "too deep" in str(error)


@pytest.mark.usefixtures("install")
def test_the_shell_diagnostic_maps_the_typed_gap_not_the_opaque_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from archkeel.cli.core_frame import Gap

    def refused(*args: object, **kwargs: object) -> None:
        raise CoreError("opaque message", gap=Gap(GapKind.PARSE_WORK_LIMIT, "source", "too deep"))

    monkeypatch.setattr(native_core.NativeCore, "decide", refused)
    with case_root(HONEST) as root:
        code, result = report(root, "--native-core")
        assert code == 2
        assert "parse_work_limit" in diagnostics(result)
        assert "source: too deep" in diagnostics(result)
        assert not (root.parent / "out/architecture.json").exists()


def canonical(root: Path) -> Path:
    text = str(root.resolve())
    # Rust canonicalize keeps the Windows verbatim prefix in a scan identity.
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        text = "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text
    return Path(text)


@pytest.fixture(scope="module")
def release_core() -> Path:
    if shutil.which("cargo") is None:
        pytest.skip("cargo is not installed")
    target = ROOT / "native/target"
    target.mkdir(exist_ok=True)
    with FileLock(str(target / ".pytest-native-build.lock")):
        subprocess.run(
            ["cargo", "build", "--release", "--locked", "-p", "archkeel-core"],
            cwd=ROOT / "native",
            env={**os.environ, "ARCHKEEL_VERSION": package_version()},
            capture_output=True,
            check=True,
            timeout=600,
        )
    suffix = ".exe" if os.name == "nt" else ""
    return ROOT / "native/target/release" / f"archkeel-core{suffix}"


def project(root: Path, files: int, depth: int, language: str = "typescript") -> dict[str, object]:
    shutil.copytree(ROOT / "fixtures/H-typescript", root)
    for args in [
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ]:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    suffix = "ts"
    if language == "rust":
        suffix = "rs"
        (root / "Cargo.toml").write_text(
            '[package]\nname="budget-probe"\nversion="0.1.0"\nedition="2021"\n'
        )
        (root / "src/lib.rs").write_text("".join(f"mod deep{number};\n" for number in range(files)))
        (root / "archkeel.toml").write_text(
            '[scan]\nlanguage="rust"\nroots=["."]\nnamespace="shop"\ncontract="architecture-contract.json"\n'
        )
    text = "(" * depth + "0" + ")" * depth + ";\n"
    for number in range(files):
        if depth == 0:
            text = "/*" + "x" * 1_000_000 + f"*/\nexport const v{number} = 1;\n"
        if language == "rust":
            text = (
                "/*" + "x" * 1_000_000 + f"*/\npub const V{number}: u8 = 1;\n"
                if depth == 0
                else "pub fn value() {" + "(" * depth + "0" + ")" * depth + ";}\n"
            )
        (root / f"src/deep{number}.{suffix}").write_text(text)
    return {
        "protocol": "archkeel-core-scan-1",
        "root": str(canonical(root)),
        "config": "archkeel.toml",
    }


def measured_scan(
    release_core: Path, request: dict[str, object]
) -> tuple[subprocess.CompletedProcess[bytes], int | None]:
    command = [str(release_core), "scan"]
    if sys.platform == "darwin":
        command = ["/usr/bin/time", "-l", *command]
    elif sys.platform.startswith("linux"):
        command = ["/usr/bin/time", "-f", "peak_kib=%M", *command]
    done = subprocess.run(
        command, input=json.dumps(request).encode(), capture_output=True, timeout=60, check=False
    )
    if sys.platform == "darwin":
        found = re.search(rb"(\d+)\s+maximum resident set size", done.stderr)
        assert found is not None, done.stderr
        peak = int(found[1])
    elif sys.platform.startswith("linux"):
        found = re.search(rb"peak_kib=(\d+)", done.stderr)
        assert found is not None, done.stderr
        peak = int(found[1]) * 1024
    else:
        return done, None
    return done, peak


@pytest.mark.parametrize(("files", "depth"), [(6, 1_992_294), (1, 1_500_000), (400, 0)])
@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_release_scans_refuse_without_a_frame_under_the_rss_bound(
    release_core: Path, tmp_path: Path, files: int, depth: int, language: str
) -> None:
    request = project(tmp_path / "project", files, depth, language)
    done, peak = measured_scan(release_core, request)
    assert done.returncode == 2, done.stderr.decode()
    assert done.stdout == b""
    assert b"parse_work_limit" in done.stderr
    bound = 300 << 20 if depth == 0 else PEAK_BOUND
    print(f"{language}: {files} files, depth {depth}: peak {peak} bytes; bound {bound} bytes")
    assert peak is None or peak < bound


def input_measurement(root: Path, manifest: Path) -> dict:
    manifest.write_text(json.dumps([("at-bound", str(canonical(root)), "archkeel.toml")]))
    done = subprocess.run(
        [
            "cargo",
            "test",
            "--locked",
            "-p",
            "archkeel-collect",
            "--lib",
            "measure_scan_input_from_public_corpus_roots",
            "--",
            "--nocapture",
        ],
        cwd=ROOT / "native",
        env={**os.environ, "ARCHKEEL_SCAN_INPUT_ROOTS": str(manifest)},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    [row] = [
        json.loads(line.removeprefix("SCAN_INPUT "))
        for line in done.stdout.splitlines()
        if line.startswith("SCAN_INPUT ")
    ]
    assert row["bound"] == 64 << 20
    return row


@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_release_scan_at_64_mib_keeps_a_full_frame_under_300_mib(
    release_core: Path, tmp_path: Path, language: str
) -> None:
    root = tmp_path / "project"
    request = project(root, 64, 0, language)
    manifest = tmp_path / "roots.json"
    padding = (64 << 20) - input_measurement(root, manifest)["charged"]
    suffix = "rs" if language == "rust" else "ts"
    path = root / f"src/deep0.{suffix}"
    text = path.read_text()
    text = text[:2] + "x" * padding + text[2:]
    assert 0 < padding and len(text) <= 4 << 20
    path.write_text(text)
    assert input_measurement(root, manifest)["charged"] == 64 << 20
    done, peak = measured_scan(release_core, request)
    assert done.returncode in (0, 3), done.stderr
    assert "request" in json.loads(done.stdout)["self_test"]["collect"]
    print(f"{language}: exactly 64 MiB input; peak {peak} bytes")
    assert peak is None or peak < 300 << 20


@pytest.mark.parametrize(
    ("language", "scope"), [("typescript", "file"), ("rust", "file"), ("rust", "scan")]
)
def test_a_forbidden_edge_after_the_cut_cannot_leave_a_rule_pass(
    release_core: Path, tmp_path: Path, language: str, scope: str
) -> None:
    root = tmp_path / "project"
    request = project(root, 0, 0, language)
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_text())
    contract.pop("declarations", None)
    owner = contract["components"][0]
    owner.update(packages=["shop"], public=["shop"], requires=[])
    contract["components"] = [owner]
    later = (
        "shop.src.zz_x5f_later_x2e_ts" if language == "typescript" else "shop.budget_probe.zz_later"
    )
    target = (
        "shop.src.zz_x5f_target_x2e_ts"
        if language == "typescript"
        else "shop.budget_probe.zz_target"
    )
    contract["rules"] = [
        {
            "id": "LATER-FORBIDDEN",
            "kind": "forbidden_dependency",
            "source": later,
            "target": target,
            "include_type_checking": True,
            "rationale": "The later edge must not escape the refusal.",
            "provenance": ["test"],
            "decided_by": "architect",
        }
    ]
    contract_path.write_text(json.dumps(contract))
    suffix = "ts" if language == "typescript" else "rs"
    count = 70 if scope == "scan" else 1
    for index in range(count):
        (root / f"src/a_pad{index:03}.{suffix}").write_text("")
    if language == "rust":
        (root / "src/lib.rs").write_text(
            "".join(f"mod a_pad{index:03};\n" for index in range(count))
            + "mod zz_later;\nmod zz_target;\n"
        )
        (root / "src/zz_later.rs").write_text("pub fn bad() {}\n")
        (root / "src/zz_target.rs").write_text("pub fn target() {}\n")
    else:
        (root / "src/zz_later.ts").write_text("export const bad = 1;\n")
        (root / "src/zz_target.ts").write_text("export function target() { return 1; }\n")
    stdout, _ = native_scan.exchange(str(release_core), "scan", json.dumps(request).encode())
    assert json.loads(stdout)["rules"]["LATER-FORBIDDEN"][1] == "PASS"
    if language == "rust":
        (root / "src/zz_later.rs").write_text("pub fn bad() { crate::zz_target::target(); }\n")
    else:
        (root / "src/zz_later.ts").write_text(
            "import { target } from './zz_target';\nexport const bad = target();\n"
        )
    stdout, _ = native_scan.exchange(str(release_core), "scan", json.dumps(request).encode())
    assert json.loads(stdout)["rules"]["LATER-FORBIDDEN"][1] == "FAIL"
    for index in range(count):
        text = (
            "/*" + "x" * 1_000_000 + "*/\n"
            if scope == "scan"
            else "(" * 1000 + "0" + ")" * 1000 + ";\n"
        )
        (root / f"src/a_pad{index:03}.{suffix}").write_text(text)
    done = subprocess.run(
        [str(release_core), "scan"],
        input=json.dumps(request).encode(),
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 2, done.stdout[:2000]
    assert done.stdout == b"" and b"PASS" not in done.stdout
    assert b"parse_work_limit" in done.stderr
    assert "a_pad" in json.loads(done.stderr)["reason"]


@pytest.mark.parametrize("shape", ["template", "jsx", "type"])
def test_nested_grammar_constructs_stay_under_300_mib(
    release_core: Path, tmp_path: Path, shape: str
) -> None:
    root = tmp_path / "project"
    request = project(root, 0, 0)
    depth = 60_000
    text = {
        "template": "const value = `text ${" + "(" * depth + "0" + ")" * depth + "}`;\n",
        "jsx": "const value = " + "<div>" * depth + "text" + "</div>" * depth + ";\n",
        "type": "type Value = " + "Array<" * depth + "number" + ">" * depth + ";\n",
    }[shape]
    suffix = "tsx" if shape == "jsx" else "ts"
    (root / f"src/nested.{suffix}").write_text(text)
    (root / "tsconfig.json").write_text(json.dumps({"include": ["src/**/*.ts", "src/**/*.tsx"]}))
    done, peak = measured_scan(release_core, request)
    assert done.returncode == 2 and done.stdout == b"", done.stderr
    assert b"parse_work_limit" in done.stderr
    assert peak is None or peak < 300 << 20


@pytest.mark.usefixtures("install")
def test_a_real_scan_work_refusal_leaves_no_shell_artifact() -> None:
    with case_root(HONEST) as root:
        root = canonical(root)
        (root / "src/deep.ts").write_text("(" * 50_000 + "0" + ")" * 50_000 + ";\n")
        python_code, _ = report(root)
        assert python_code == 0
        code, result = report(root, "--native-core")
        assert code == 2
        assert "parse_work_limit" in diagnostics(result)
        assert not (root.parent / "out/architecture.json").exists()


@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_the_shell_keeps_the_typed_refusal_of_a_real_core(
    release_core: Path, tmp_path: Path, language: str
) -> None:
    request = project(tmp_path / "project", 1, 1_500_000, language)
    with pytest.raises(CoreError) as error:
        native_scan.exchange(str(release_core), "scan", json.dumps(request).encode())
    assert error.value.gap is not None
    assert error.value.gap.kind is GapKind.PARSE_WORK_LIMIT
    assert "parse_work_limit" in str(error.value)


@pytest.mark.parametrize("workspace", [False, True], ids=["typescript-corpus", "native"])
def test_a_scan_below_both_bounds_gives_the_same_frame_as_without_the_guard(
    install: Path, monkeypatch: pytest.MonkeyPatch, workspace: bool
) -> None:
    checked = []
    plain_frames = []

    def exchange(binary: str, kind: str, payload: bytes) -> tuple[bytes, int]:
        stdout, code = native_scan.exchange(binary, kind, payload)
        plain_frames.append(json.loads(stdout))
        return stdout, code

    monkeypatch.setattr(native_core, "exchange", exchange)

    def decide(self: native_core.NativeCore, result: Any, root: Path, config: Any, *_: Any) -> Any:
        assert self.binary is not None
        # The bundled subprocess collector has no in-process guard.
        plain = self.run(
            self.binary, config, partial(native_core.read_inside, root), self.replies[0], None
        )
        config_path = "native/archkeel.toml" if workspace else "archkeel.toml"
        request = native_scan.scan_request(self.requests[0], config_path)
        stdout, _ = native_scan.exchange(str(self.binary), "scan", json.dumps(request).encode())
        scanned = json.loads(stdout)
        # Only scan carries self_test.collect; every other wire-frame field must match.
        assert "request" in scanned["self_test"].pop("collect")
        [unbounded] = plain_frames
        assert scanned == unbounded
        if workspace:
            assert "the collector reports" not in plain.scope, plain.scope
        checked.append(plain)
        return result

    monkeypatch.setattr(native_core.NativeCore, "decide", decide)
    if workspace:
        from graph_report_support import commit_tree

        root = install.parent / "project"
        shutil.copytree(ROOT / "native", root / "native", ignore=shutil.ignore_patterns("target"))
        commit_tree(root)
        monkeypatch.chdir(root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(
                [
                    "report",
                    "--config",
                    "native/archkeel.toml",
                    "--json",
                    "--native-core",
                    "--output",
                    str(install.parent / "out/architecture.json"),
                ]
            )
        assert checked, output.getvalue()
    else:
        with case_root(HONEST) as root:
            report(root, "--native-core")
    assert len(checked) == 1


@pytest.mark.parametrize(
    "stderr",
    [
        b"parse_work_limit: planted text",
        b'{"kind":"parse_work_limit"}',
        b'{"protocol":"wrong","kind":"parse_work_limit","subject":"scan","reason":"x"}',
        b'{"protocol":"archkeel-core-refusal-1","kind":"other","subject":"scan","reason":"x"}',
    ],
)
def test_a_text_prefix_or_an_incomplete_object_cannot_set_the_kind(
    monkeypatch: pytest.MonkeyPatch, stderr: bytes
) -> None:
    def refused(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess([], 2, b"", stderr)

    monkeypatch.setattr(native_scan.subprocess, "run", refused)
    with pytest.raises(CoreError) as error:
        native_scan.exchange("core", "scan", b"{}")
    assert error.value.gap is None
