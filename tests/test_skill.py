# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Tests for installing the Archkeel coding-agent skill."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from archkeel.cli.skill import install_skill

ROOT = Path(__file__).parents[1]
ASSET = ROOT / "src" / "archkeel" / "cli" / "assets" / "SKILL.md"


def test_claude_writes_the_asset_unchanged(tmp_path: Path) -> None:
    target = install_skill(tmp_path, "claude")
    assert target == tmp_path / ".claude" / "skills" / "archkeel" / "SKILL.md"
    assert target.read_bytes() == ASSET.read_bytes()


def test_claude_install_is_idempotent(tmp_path: Path) -> None:
    first = install_skill(tmp_path, "claude")
    before = first.read_bytes()
    second = install_skill(tmp_path, "claude")
    assert second.read_bytes() == before


def test_codex_writes_native_skill_unchanged(tmp_path: Path) -> None:
    path = install_skill(tmp_path, "codex")
    assert path == tmp_path / ".agents" / "skills" / "archkeel" / "SKILL.md"
    assert path.read_bytes() == ASSET.read_bytes()
    assert not (tmp_path / "AGENTS.md").exists()


def test_codex_preserves_surrounding_user_text(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("Existing content untouched.\n\nMore notes.\n", encoding="utf-8")
    install_skill(tmp_path, "codex")
    text = agents.read_text(encoding="utf-8")
    assert text == "Existing content untouched.\n\nMore notes.\n"


def test_codex_migrates_only_the_managed_section(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "Before.\n\n<!-- archkeel:start -->\nstale body\n<!-- archkeel:end -->\n\nAfter.\n",
        encoding="utf-8",
    )
    install_skill(tmp_path, "codex")
    text = agents.read_text(encoding="utf-8")
    assert text == "Before.\n\n\n\nAfter.\n"
    assert (tmp_path / ".agents/skills/archkeel/SKILL.md").read_bytes() == ASSET.read_bytes()


def test_codex_preserves_crlf_outside_legacy_block(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_bytes(b"Before\r\n<!-- archkeel:start -->old<!-- archkeel:end -->\r\nAfter\r\n")
    install_skill(tmp_path, "codex")
    assert agents.read_bytes() == b"Before\r\n\r\nAfter\r\n"


def test_codex_install_is_idempotent(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("Notes.\n", encoding="utf-8")
    install_skill(tmp_path, "codex")
    first = agents.read_bytes()
    install_skill(tmp_path, "codex")
    assert agents.read_bytes() == first


def test_codex_install_preserves_physical_review_threshold_guidance(tmp_path: Path) -> None:
    body = ASSET.read_text(encoding="utf-8")
    path = install_skill(tmp_path, "codex")
    installed = path.read_text(encoding="utf-8")

    assert "More than seven direct children triggers a review" in body
    assert "Five to seven understandable groups is a review heuristic" in body
    assert "do not hide the excess in `misc`, `utils`, single-child wrappers" in body
    assert installed == body


@pytest.mark.parametrize(
    "markers",
    [
        "<!-- archkeel:start -->\nbroken\n",
        "<!-- archkeel:end -->\n",
        "<!-- archkeel:end --><!-- archkeel:start -->",
        "<!-- archkeel:start --><!-- archkeel:start --><!-- archkeel:end -->",
    ],
)
def test_codex_rejects_malformed_markers_before_writing(tmp_path: Path, markers: str) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text(markers, encoding="utf-8")
    with pytest.raises(ValueError, match="marker"):
        install_skill(tmp_path, "codex")
    assert agents.read_text(encoding="utf-8") == markers
    assert not (tmp_path / ".agents").exists()


def test_skill_covers_interview_and_auto_mode() -> None:
    """AD-16: the skill must name both onboarding modes, not just the interview."""
    body = ASSET.read_text(encoding="utf-8")
    assert "Interview mode" in body
    assert "Auto mode" in body
    assert 'decided_by: "architect"' in body
    assert 'decided_by: "agent"' in body


def test_skill_asks_why_on_a_deviation_from_its_recommendation() -> None:
    """AD-16: interview mode asks why before writing a rule against its own recommendation."""
    body = ASSET.read_text(encoding="utf-8")
    assert "ask why before writing the rule" in body


def test_plugin_package_uses_the_canonical_skill_and_refuses_overwrite(tmp_path: Path) -> None:
    # Codex's plugin loader skips linked SKILL.md files.
    assert not (ROOT / "skills/archkeel/SKILL.md").is_symlink()
    target = tmp_path / "plugin"
    command = [sys.executable, "-m", "tools.package_plugin", str(target)]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert (target / "skills/archkeel/SKILL.md").read_bytes() == ASSET.read_bytes()
    portable = json.loads((target / "plugin.json").read_text())
    claude = json.loads((target / ".claude-plugin/plugin.json").read_text())
    assert portable["name"] == claude["name"] == "archkeel"
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert "mcpServers" not in portable and "hooks" not in portable
    assert (ROOT / "skills/archkeel/SKILL.md").read_bytes() == ASSET.read_bytes()
    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert marketplace["plugins"] == [{"name": "archkeel", "source": "./"}]
    codex_marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert codex_marketplace["plugins"][0]["source"] == {"source": "local", "path": "./"}
    with zipfile.ZipFile(Path(str(target) + ".zip")) as bundle:
        assert bundle.read("skills/archkeel/SKILL.md") == ASSET.read_bytes()
        assert "docs/assets/archkeel-mark.svg" in bundle.namelist()
    sentinel = target / "user-notes.txt"
    sentinel.write_text("Keep me")
    rerun = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert rerun.returncode != 0
    assert sentinel.read_text() == "Keep me"


def test_plugin_export_preserves_an_existing_zip(tmp_path: Path) -> None:
    target = tmp_path / "plugin.v1"
    archive = Path(str(target) + ".zip")
    archive.write_bytes(b"User file")
    run = subprocess.run(
        [sys.executable, "-m", "tools.package_plugin", str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0
    assert archive.read_bytes() == b"User file"
    assert not target.exists()


def test_directory_plugin_stays_current_regular_and_within_submission_limits(
    tmp_path: Path,
) -> None:
    target = tmp_path / "plugin"
    run = subprocess.run(
        [sys.executable, "-m", "tools.package_plugin", str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert len("\n".join(readme.splitlines()[2:]).split()) >= 40
    assert "```" not in readme
    portable = json.loads((target / "plugin.json").read_text())
    interface = portable["extensions"]["com.openai"]["interface"]
    assert portable["description"] in readme
    assert interface["longDescription"] in readme
    assert (target / interface["composerIcon"]).is_file()

    paths = {
        "README.md",
        "LICENSE",
        "plugin.json",
        ".claude-plugin/plugin.json",
        "skills/archkeel/SKILL.md",
        "docs/assets/archkeel-mark.svg",
    }
    files = {path.relative_to(target).as_posix(): path for path in target.rglob("*")}
    assert all(not path.is_symlink() for path in files.values())
    files = {name: path for name, path in files.items() if path.is_file()}
    assert set(files) == paths
    assert len(files) <= 512
    for name, path in files.items():
        assert path.stat().st_size < 5 * 1024 * 1024, name
        if path.suffix != ".svg":
            assert path.stat().st_size < 256 * 1024, name
    with zipfile.ZipFile(Path(str(target) + ".zip")) as bundle:
        assert {item.filename for item in bundle.infolist() if not item.is_dir()} == paths
        assert all(bundle.read(name) == (target / name).read_bytes() for name in paths)


def test_plugin_release_requires_matching_explicit_version_before_output(tmp_path: Path) -> None:
    version = json.loads((ROOT / "plugin.json").read_text())["version"]
    target = tmp_path / "release"
    command = [sys.executable, "-m", "tools.package_plugin", str(target), "--expected-version"]
    rejected = subprocess.run(command + [version + ".wrong"], cwd=ROOT, capture_output=True)
    assert rejected.returncode != 0
    assert not target.exists()
    built = subprocess.run(command + [version], cwd=ROOT, capture_output=True)
    assert built.returncode == 0, built.stderr
    archive = Path(str(target) + ".zip")
    checked = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.package_plugin",
            str(archive),
            "--check",
            "--expected-version",
            version,
        ],
        cwd=ROOT,
        capture_output=True,
    )
    assert checked.returncode == 0, checked.stderr
    Path(str(archive) + ".sha256").write_text("wrong checksum\n")
    rejected = subprocess.run(
        [sys.executable, "-m", "tools.package_plugin", str(archive), "--check"],
        cwd=ROOT,
        capture_output=True,
    )
    assert rejected.returncode != 0


@pytest.mark.parametrize("damage", ["missing", "duplicate", "manifest", "unexpected"])
def test_plugin_release_rejects_malformed_zip_even_with_matching_checksum(
    tmp_path: Path,
    damage: str,
) -> None:
    import hashlib

    target = tmp_path / "release"
    built = subprocess.run(
        [sys.executable, "-m", "tools.package_plugin", str(target)],
        cwd=ROOT,
        capture_output=True,
    )
    assert built.returncode == 0, built.stderr
    archive = Path(str(target) + ".zip")
    with zipfile.ZipFile(archive) as bundle:
        files = {
            entry.filename: bundle.read(entry) for entry in bundle.infolist() if not entry.is_dir()
        }
    if damage == "missing":
        del files["skills/archkeel/SKILL.md"]
    elif damage == "manifest":
        files["plugin.json"] = b"malformed"
    elif damage == "unexpected":
        files["../unexpected"] = b"not distributable"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
        if damage == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate name"):
                bundle.writestr("plugin.json", files["plugin.json"])
    Path(str(archive) + ".sha256").write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n"
    )
    checked = subprocess.run(
        [sys.executable, "-m", "tools.package_plugin", str(archive), "--check"],
        cwd=ROOT,
        capture_output=True,
    )
    assert checked.returncode != 0


@pytest.mark.parametrize("release_version", [None, "5.0.1"])
def test_plugin_release_rejects_disagreeing_manifest_versions(
    tmp_path: Path, monkeypatch, release_version: str | None
) -> None:
    from tools import package_plugin

    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / "plugin.json").write_bytes((ROOT / "plugin.json").read_bytes())
    claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    claude["version"] = "0.0.0"
    (tmp_path / ".claude-plugin/plugin.json").write_text(json.dumps(claude))
    monkeypatch.setattr(package_plugin, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="release version"):
        package_plugin._plugin_files(None, release_version)


@pytest.mark.parametrize(
    ("source_version", "release_version"), [("3.0.1", "4.0.1"), ("5.0.0", "5.0.1")]
)
def test_plugin_release_stamps_only_exported_manifests(
    tmp_path: Path, monkeypatch, source_version: str, release_version: str
) -> None:
    from tools import package_plugin

    source = tmp_path / "source"
    names = (
        "plugin.json",
        ".claude-plugin/plugin.json",
        "skills/archkeel/SKILL.md",
        "LICENSE",
        "src/archkeel/render/assets/archkeel-mark.svg",
    )
    for name in names:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (ROOT / name).read_bytes()
        if name.endswith("plugin.json"):
            metadata = json.loads(content)
            metadata["version"] = source_version
            content = (json.dumps(metadata, indent=2) + "\n").encode()
        path.write_bytes(content)
    before = {name: (source / name).read_bytes() for name in names}
    monkeypatch.setattr(package_plugin, "ROOT", source)
    canonical = package_plugin._plugin_files(source_version)
    target = tmp_path / "export"
    arguments = ["package_plugin", str(target), "--release-version", release_version]
    monkeypatch.setattr(sys, "argv", arguments + ["--expected-version", source_version])
    with pytest.raises(ValueError, match="release version"):
        package_plugin.main()
    assert not target.exists() and not Path(str(target) + ".zip").exists()
    monkeypatch.setattr(sys, "argv", arguments + ["--expected-version", release_version])
    package_plugin.main()
    archive = Path(str(target) + ".zip")
    expected = package_plugin._plugin_files(release_version, release_version)
    package_plugin._check_bundle(archive, expected)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_plugin",
            str(archive),
            "--check",
            "--release-version",
            release_version,
            "--expected-version",
            release_version,
        ],
    )
    package_plugin.main()
    repeated = tmp_path / "repeated"
    monkeypatch.setattr(
        sys, "argv", ["package_plugin", str(repeated), "--release-version", release_version]
    )
    package_plugin.main()
    assert Path(str(repeated) + ".zip").read_bytes() == archive.read_bytes()
    assert {name: (source / name).read_bytes() for name in names} == before
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == set(canonical)
        for name, original in canonical.items():
            actual = bundle.read(name)
            if name.endswith("plugin.json"):
                metadata = json.loads(actual)
                assert metadata.pop("version") == release_version
                original_metadata = json.loads(original)
                original_metadata.pop("version")
                assert metadata == original_metadata
            else:
                assert actual == original
    for manifest in ("plugin.json", ".claude-plugin/plugin.json"):
        damaged = dict(expected)
        damaged[manifest] = canonical[manifest]
        with zipfile.ZipFile(archive, "w") as bundle:
            for name, content in damaged.items():
                bundle.writestr(name, content)
        Path(str(archive) + ".sha256").write_text(package_plugin._checksum(archive))
        with pytest.raises(ValueError, match="differs from canonical source"):
            package_plugin._check_bundle(archive, expected)


@pytest.mark.parametrize(
    ("mode", "directory", "dos_attributes", "accepted"),
    [
        (0o120777, False, 0, False),
        (0o010644, False, 0, False),
        (0o020644, False, 0, False),
        (0o060644, False, 0, False),
        (0o140644, False, 0, False),
        (0o120777, True, 0x10, False),
        (0o100644, True, 0x10, False),
        (0, True, 0, False),
        (0, False, 0x20, True),
        (0, True, 0x10, True),
    ],
)
def test_plugin_release_validates_entry_types_with_valid_checksums(
    tmp_path: Path,
    mode: int,
    directory: bool,
    dos_attributes: int,
    accepted: bool,
) -> None:
    from tools import package_plugin

    files = package_plugin._plugin_files(None)
    archive = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, content in files.items():
            entry = zipfile.ZipInfo(name)
            entry.create_system = 0
            entry.external_attr = 0x20
            if name == "plugin.json" and not directory:
                entry.external_attr = mode << 16 | dos_attributes
            bundle.writestr(entry, content)
        if directory:
            entry = zipfile.ZipInfo("skills/")
            entry.create_system = 0
            entry.external_attr = mode << 16 | dos_attributes
            bundle.writestr(entry, b"")
    Path(str(archive) + ".sha256").write_text(package_plugin._checksum(archive))
    if accepted:
        package_plugin._check_bundle(archive, files)
    else:
        with pytest.raises(ValueError, match="entry metadata"):
            package_plugin._check_bundle(archive, files)


def test_plugin_release_zip_is_identical_when_local_time_changes(
    tmp_path: Path, monkeypatch
) -> None:
    import time

    from tools import package_plugin

    archives = []
    for name, year in [("first", 2020), ("second", 2030)]:
        monkeypatch.setattr(
            time, "localtime", lambda *args, year=year: (year, 2, 3, 4, 5, 6, 0, 1, 0)
        )
        target = tmp_path / name
        monkeypatch.setattr(sys, "argv", ["package_plugin", str(target)])
        package_plugin.main()
        archives.append(Path(str(target) + ".zip").read_bytes())
    assert archives[0] == archives[1]
    with zipfile.ZipFile(tmp_path / "first.zip") as bundle:
        assert bundle.namelist() == sorted(package_plugin._plugin_files(None))
        assert all(entry.date_time == (1980, 1, 1, 0, 0, 0) for entry in bundle.infolist())
        assert all(entry.external_attr >> 16 == 0o100644 for entry in bundle.infolist())
