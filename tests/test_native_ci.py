# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-316, AD-317, AD-436, AD-476: CI checks the native code; a release has six platform wheels."""

from __future__ import annotations

import hashlib
import re
import subprocess
import zipfile
from pathlib import Path
from textwrap import dedent

import pytest

from tools import release_core
from tools.publish_release import PLATFORM_TAGS

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def _jobs(workflow: str) -> dict[str, str]:
    text = (WORKFLOWS / workflow).read_text()
    parts = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_every_action_is_pinned_to_a_commit() -> None:
    # A tag can move to other code; a commit SHA cannot.
    for path in WORKFLOWS.glob("*.yml"):
        for action in re.findall(r"^\s+(?:- )?uses: (\S+)", path.read_text(), re.MULTILINE):
            if not action.startswith("./"):
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", action), (path.name, action)


def _add_script() -> str:
    build = _jobs("release.yml")["build"]
    assert "pattern: native-wheel-*\n" in build and "path: build/native-wheels/\n" in build
    step = build.split("- name: Add the platform wheels that full verification built and ran\n")
    return dedent(step[1].split("        run: |\n", 1)[1].split("\n\n", 1)[0])


def test_a_release_adds_every_platform_wheel_of_full(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "build/native-wheels").mkdir(parents=True)
    (tmp_path / "dist/archkeel-5.0.0.tar.gz").write_bytes(b"sdist")
    for tag in PLATFORM_TAGS:
        (tmp_path / "build/native-wheels" / f"archkeel-5.0.0-{tag}.whl").write_bytes(b"wheel")
    result = subprocess.run(
        ["bash", "-c", _add_script()], cwd=tmp_path, check=False, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / "dist").glob("*.whl"))) == len(PLATFORM_TAGS)
    assert len(list((tmp_path / "dist").glob("*.tar.gz"))) == 1


@pytest.mark.parametrize("wheels,sdists", [(n, 1) for n in range(8)] + [(6, 0), (6, 2)])
@pytest.mark.parametrize("pure", ["", "dist", "build/native-wheels"])
def test_release_requires_exactly_six_platform_wheels_and_one_sdist(
    tmp_path: Path, wheels: int, sdists: int, pure: str
) -> None:
    """A wheel without a platform carries no core (AD-436): it stops the step where it is."""
    script = _add_script()
    (tmp_path / "dist").mkdir()
    (tmp_path / "build/native-wheels").mkdir(parents=True)
    if pure:
        (tmp_path / pure / "archkeel-5.0.0-py3-none-any.whl").write_bytes(b"pure")
    for index in range(wheels - (pure == "build/native-wheels")):
        (
            tmp_path / "build/native-wheels" / f"archkeel-5.0.0-py3-none-platform{index}.whl"
        ).write_bytes(b"wheel")
    for index in range(sdists):
        (tmp_path / "dist" / f"archkeel-5.0.{index}.tar.gz").write_bytes(b"sdist")
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is (wheels == 6 and sdists == 1 and not pure)
    if result.returncode == 0:
        assert len(list((tmp_path / "dist").glob("*.whl"))) == 6


def test_release_wheel_staging_does_not_dirty_the_checkout(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text((ROOT / ".gitignore").read_text())
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "init",
        ],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "dist").mkdir()
    (tmp_path / "build/native-wheels").mkdir(parents=True)
    (tmp_path / "dist/archkeel-5.0.0.tar.gz").write_bytes(b"sdist")
    for tag in PLATFORM_TAGS:
        (tmp_path / "build/native-wheels" / f"archkeel-5.0.0-{tag}.whl").write_bytes(b"wheel")
    subprocess.run(["bash", "-c", _add_script()], cwd=tmp_path, check=True)
    from archkeel.cli.native_scan import identity

    assert identity(tmp_path)[1] is False
    (tmp_path / "untracked-source.py").write_text("pass\n")
    assert identity(tmp_path)[1] is True


def _wheel(directory: Path, tag: str, *members: str, digest: str = "") -> Path:
    """A wheel with the members; a `.sha256` member holds the digest of the other members."""
    wheel = directory / f"archkeel-5.0.0-{tag}.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for member in ("archkeel/__init__.py", *members):
            recorded = digest or hashlib.sha256(b"x").hexdigest()
            archive.writestr(member, recorded if member.endswith(".sha256") else "x")
    return wheel


def _binaries(suffix: str = "") -> tuple[str, ...]:
    return tuple(
        base + suffix + end
        for base in (release_core.MEMBER, *release_core.WORKERS)
        for end in ("", ".sha256")
    )


def test_a_wheel_carries_the_core_only_with_the_binary_and_its_digest(tmp_path: Path) -> None:
    core = release_core.MEMBER
    assert core == "archkeel/_native/archkeel-core"
    assert not release_core.carries_core(_wheel(tmp_path, "a", "archkeel/_native/collector"))
    assert not release_core.carries_core(_wheel(tmp_path, "b", core))
    assert not release_core.carries_core(_wheel(tmp_path, "c", core + ".sha256"))
    assert not release_core.carries_core(_wheel(tmp_path, "d", core, core + ".exe.sha256"))
    assert not release_core.carries_core(_wheel(tmp_path, "e", core, core + ".sha256"))
    assert release_core.carries_core(_wheel(tmp_path, "py3-none-host", *_binaries()))
    assert release_core.carries_core(_wheel(tmp_path, "py3-none-win_amd64", *_binaries(".exe")))
    # A digest of other bytes makes the shell refuse the binary, so the wheel carries no core.
    other = hashlib.sha256(b"other").hexdigest()
    assert not release_core.carries_core(_wheel(tmp_path, "g", *_binaries(), digest=other))
    assert not release_core.carries_core(_wheel(tmp_path, "h", core, core + ".sha256", digest="x"))
    (tmp_path / "no-archive.whl").write_bytes(b"wheel")
    assert not release_core.carries_core(tmp_path / "no-archive.whl")


def test_the_release_check_refuses_each_wheel_without_the_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    core = release_core.MEMBER
    monkeypatch.setattr(release_core, "platform_tags", lambda: ("py3-none-host",))
    assert release_core.main([str(tmp_path), "x.whl"]) == 2
    host = _wheel(tmp_path, "py3-none-host", *_binaries())
    bare = _wheel(tmp_path, "py3-none-other")
    ran: list[Path] = []
    monkeypatch.setattr(release_core, "smoke", lambda wheel: ran.append(wheel) or "")
    assert release_core.main([str(tmp_path), str(host)]) == 2
    assert f"release refused: {bare.name} does not carry {core}" in capsys.readouterr().err
    # No installed run stands in for a wheel without the core.
    assert ran == []
    bare.unlink()
    assert release_core.main([str(tmp_path), str(tmp_path / "absent.whl")]) == 2 and ran == []
    assert release_core.main([str(tmp_path), str(host)]) == 0 and ran == [host]
    monkeypatch.setattr(release_core, "smoke", lambda wheel: "refusal core_binary_not_found")
    assert release_core.main([str(tmp_path), str(host)]) == 2
    assert "gives no verdict of its core: refusal core_binary_not_found" in capsys.readouterr().err
    assert release_core.main([str(tmp_path)]) == 2


def test_the_release_check_wants_exactly_the_platforms_of_the_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-476: a missing or an unlisted platform stops the release; each listed one passes."""
    host = _wheel(tmp_path, "py3-none-host", *_binaries())
    windows = _wheel(tmp_path, "py3-none-win_amd64", *_binaries(".exe"))
    ran: list[Path] = []
    monkeypatch.setattr(release_core, "smoke", lambda wheel: ran.append(wheel) or "")
    monkeypatch.setattr(
        release_core, "platform_tags", lambda: ("py3-none-host", "py3-none-win_amd64")
    )
    assert release_core.main([str(tmp_path), str(host)]) == 0 and ran == [host]
    windows.unlink()
    assert release_core.main([str(tmp_path), str(host)]) == 2
    assert "are not exactly the platforms" in capsys.readouterr().err
    windows = _wheel(tmp_path, "py3-none-win_amd64", *_binaries(".exe"))
    monkeypatch.setattr(release_core, "platform_tags", lambda: ("py3-none-host",))
    assert release_core.main([str(tmp_path), str(host)]) == 2
    assert "are not exactly the platforms" in capsys.readouterr().err


def test_only_a_verdict_of_the_bundled_core_passes_the_installed_run() -> None:
    frame = {"engine": "archkeel-core 0a", "rules": {"R": ["root_layout", "PASS"]}}
    core = {"path": "/venv/site-packages/archkeel/_native/archkeel-core"}
    good = {"status": "UNKNOWN", "exit_code": 2, "frame": frame, "core": core}
    assert release_core.undecided(good, 2) == ""
    refusal = {"status": "UNKNOWN", "exit_code": 2, "refusal": {"kind": "core_binary_not_found"}}
    assert release_core.undecided(refusal, 2) == "refusal core_binary_not_found"
    assert release_core.undecided([], 2) == "no result object: []"
    assert "no frame" in release_core.undecided({**good, "frame": {**frame, "engine": "x"}}, 2)
    checkout = {"path": "/checkout/native/target/release/archkeel-core"}
    assert "not the binary of the package" in release_core.undecided({**good, "core": checkout}, 2)
    unknown = {**frame, "rules": {"R": ["root_layout", "UNKNOWN"]}}
    assert "no rule has PASS" in release_core.undecided({**good, "frame": unknown}, 2)
    assert "exit code 0 differs" in release_core.undecided(good, 0)
