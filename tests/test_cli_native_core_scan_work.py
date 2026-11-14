# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-420: release scan refusals bound parse work before any syntax tree exists."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from core_support import EMPTY_GRAPH, HONEST, ROOT, case_root, ensure_target_dir, run
from filelock import FileLock

from archkeel.cli import core_only, native_scan
from archkeel.cli.core_frame import CoreError, GapKind

PEAK_BOUND = 128 * 1024 * 1024


def test_the_printed_core_error_uses_its_typed_gap() -> None:
    from archkeel.cli.core_frame import Gap

    error = CoreError("untyped message", gap=Gap(GapKind.PARSE_WORK_LIMIT, "source", "too deep"))
    assert "parse_work_limit" in str(error)
    assert "source" in str(error)
    assert "too deep" in str(error)


def test_the_shell_refusal_names_the_typed_gap_not_the_opaque_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from archkeel.cli.core_frame import Gap

    def refused(*args: object, **kwargs: object) -> None:
        raise CoreError("opaque message", gap=Gap(GapKind.PARSE_WORK_LIMIT, "source", "too deep"))

    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", refused)
    code, result = run("validate", "--root", str(tmp_path))
    assert code == 2 and result["status"] == "UNKNOWN"
    assert "frame" not in result
    assert result["refusal"]["kind"] == "core_error"
    assert "parse_work_limit" in result["refusal"]["message"]
    assert "source: too deep" in result["refusal"]["message"]


def canonical(root: Path) -> Path:
    text = str(root.resolve())
    # Rust canonicalize keeps the Windows verbatim prefix in a scan identity.
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        text = "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text
    return Path(text)


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
    ensure_target_dir(ROOT / "native")
    # The build lock of all workers: cargo must not build in the shared target at the same time.
    with FileLock(str(ROOT / "native/target/.pytest-native-build.lock")):
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
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    ]
    contract_path.write_text(json.dumps(contract))
    (root / "docs/architecture/shop.md").write_text(EMPTY_GRAPH)
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


@pytest.mark.parametrize("command", ["validate", "report"])
def test_a_real_scan_work_refusal_is_a_typed_refusal_of_the_default_path(
    core_binary: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: core_binary)
    with case_root(HONEST) as root:
        code, honest = run(command, "--root", str(root))
        assert (code, honest["status"]) == (0, "PASS")
        (root / "src/deep.ts").write_text("(" * 50_000 + "0" + ")" * 50_000 + ";\n")
        code, result = run(command, "--root", str(root))
    assert code == 2 and result["status"] == "UNKNOWN"
    assert "frame" not in result
    assert result["refusal"]["kind"] == "core_error"
    assert "parse_work_limit" in result["refusal"]["message"]


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
