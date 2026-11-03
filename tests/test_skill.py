# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Tests for installing the Archkeel coding-agent skill."""

import contextlib
import io
import json
import re
import shlex
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from archkeel.cli import build_parser, main
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


def _flow_section() -> str:
    body = ASSET.read_text(encoding="utf-8")
    start = body.find("## Show a flow\n")
    end = body.find("\n## ", start + 1)
    return body[start:end] if start != -1 else ""


def _parses(argv: list[str]) -> bool:
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            build_parser().parse_args(argv)
    except ValueError:  # _Parser.error raises it instead of exiting
        return False
    return True


_FLOW_COMMANDS = re.findall(r"`(archkeel [^`]+)`", _flow_section())
# Commands of strands that are not on main yet, with a minimal valid call. Delete each after merge.
_PENDING = {"explore": ["explore"], "view show": ["view", "show", "flow.json"]}


def test_flow_section_teaches_the_whole_loop() -> None:
    assert len(_FLOW_COMMANDS) >= 6
    taught = {" ".join(command.split()[1:3]) for command in _FLOW_COMMANDS}
    assert {"report --input", "view check", "view show"} <= taught
    assert any(command.startswith("archkeel explore") for command in _FLOW_COMMANDS)


@pytest.mark.parametrize("command", _FLOW_COMMANDS)
def test_flow_section_command_parses_with_the_real_cli(command: str) -> None:
    """#787: each command line the skill teaches exists in the CLI with these options."""
    argv = shlex.split(re.sub(r"<[^>]+>", "x", command))[1:]
    pending = next((call for name, call in _PENDING.items() if command[9:].startswith(name)), None)
    if pending is not None and not _parses(pending):
        pytest.skip(f"{command[9:]} is not merged into this branch yet")
    assert _parses(argv), command


def test_flow_section_states_the_proof_rules() -> None:
    section = _flow_section()
    assert '"claim": true' in section
    assert "`unknown`" in section and "`missing`" in section
    assert "not runtime order" in section
    assert "except as a claim" in section
    assert "`path`" in section
    assert "`status` or `evidence`" in section
    assert "not an execution trace" in section
    assert "`target: unavailable`" in section
    # The same file serves Codex and Claude Code: name commands, not one agent's tools.
    assert not re.search(r"\b(Read|Bash|Edit|Write) tool\b", section)


_VIEW_SHOW = pytest.mark.skipif(
    not _parses(_PENDING["view show"]), reason="view show (#786) is not merged yet"
)


@pytest.fixture(scope="module")
def shop_snapshot(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Step 2 of the section: a contract repository gets its snapshot from `report`."""
    from test_architecture_demo import _prepare_repo

    root = _prepare_repo(tmp_path_factory.mktemp("flow"), {})
    snapshot = root.parent / "snapshot" / "architecture.json"
    assert main(["report", "--root", str(root), "--output", str(snapshot), "--json"]) == 0
    return snapshot


def _agent_spec(snapshot: Path, steps: list[str], edges: list[dict]) -> dict:
    """Write the spec the way the section says: digests copied, a kind on each link."""
    packet = json.loads(snapshot.read_text())
    return {
        "schema_version": "1.0.0",
        "title": "How does the CLI place an order?",
        "snapshot": {
            "source_digest": packet["source"]["source_digest"],
            "contract_digest": packet["contract"]["digest"],
        },
        "nodes": sorted({*steps, *(e[end] for e in edges for end in ("source", "target"))}),
        "steps": [
            {"node": steps[0]},
            *({"node": node, "kind": "imports"} for node in steps[1:]),
        ],
        "edges": edges,
        "notes": ["Author text: the agent explains the flow; the check proves structure."],
    }


def _view(
    command: str, tmp_path: Path, snapshot: Path, spec: dict, capsys: pytest.CaptureFixture
) -> tuple[int, dict]:
    path = tmp_path / "views" / "flow.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(spec))
    extra = ["--output", str(tmp_path / "page")] if command == "show" else []
    code = main(["view", command, str(path), "--snapshot", str(snapshot), "--json", *extra])
    out = capsys.readouterr().out
    return code, json.loads(out) if code != 2 else {}


_PLACE_ORDER = ["shop.cli.main", "shop.app.orders", "shop.store", "shop.store.repository"]
_INVENTED = {"source": "shop.app.orders", "target": "shop.render.text", "kind": "imports"}


def test_agent_flow_proves_each_step_with_evidence_and_keeps_the_claim(
    tmp_path: Path, shop_snapshot: Path, capsys: pytest.CaptureFixture
) -> None:
    claim = {**_INVENTED, "claim": True, "note": "orders prints the receipt (invented)."}
    spec = _agent_spec(shop_snapshot, _PLACE_ORDER, [claim])
    code, result = _view("check", tmp_path, shop_snapshot, spec, capsys)
    assert code == 0 and result["snapshot_current"]
    assert result["snapshot"] == result["view_snapshot"] == spec["snapshot"]
    assert result["edges"][0]["status"] == "claim" and not result["edges"][0].get("evidence")
    for step in result["steps"][1:]:
        assert step["status"] == "proven" and len(step["path"]) == 2, step
        assert all(
            item["file"] and item["line"] and item["evidence_id"] for item in step["evidence"]
        )
    assert "not runtime order" in result["limits"][0]


def test_agent_flow_invented_import_is_missing_and_a_skipped_hop_shows_in_path(
    tmp_path: Path, shop_snapshot: Path, capsys: pytest.CaptureFixture
) -> None:
    steps = ["shop.cli.main", "shop.app.orders", "shop.store.repository"]
    code, result = _view(
        "check", tmp_path, shop_snapshot, _agent_spec(shop_snapshot, steps, [_INVENTED]), capsys
    )
    assert code == 1 and result["edges"][0]["status"] == "missing"
    # The re-export hop the author did not name: the section says to add it as a step.
    assert result["steps"][2]["path"] == ["shop.app.orders", "shop.store", "shop.store.repository"]


def test_agent_flow_invented_call_is_unknown_never_missing(
    tmp_path: Path, shop_snapshot: Path, capsys: pytest.CaptureFixture
) -> None:
    invented = {**_INVENTED, "kind": "calls"}
    code, result = _view(
        "check",
        tmp_path,
        shop_snapshot,
        _agent_spec(shop_snapshot, _PLACE_ORDER, [invented]),
        capsys,
    )
    assert code == 0 and result["edges"][0]["status"] == "unknown"
    assert "call" in result["edges"][0]["reason"]


def test_agent_flow_spec_cannot_state_proof(
    tmp_path: Path, shop_snapshot: Path, capsys: pytest.CaptureFixture
) -> None:
    forged = {**_INVENTED, "status": "proven"}
    spec = _agent_spec(shop_snapshot, _PLACE_ORDER, [forged])
    assert _view("check", tmp_path, shop_snapshot, spec, capsys)[0] == 2


@_VIEW_SHOW
def test_agent_flow_show_writes_the_page_with_the_checked_result(
    tmp_path: Path, shop_snapshot: Path, capsys: pytest.CaptureFixture
) -> None:
    claim = {**_INVENTED, "claim": True}
    spec = _agent_spec(shop_snapshot, _PLACE_ORDER, [claim])
    code, checked = _view("check", tmp_path, shop_snapshot, spec, capsys)
    assert code == 0
    assert _view("show", tmp_path, shop_snapshot, spec, capsys) == (0, checked)
    page = (tmp_path / "page" / "architecture.report.html").read_text()
    embedded = re.search(
        r'<script id="view-check-data" type="application/json">(.*?)</script>', page, re.S
    )
    assert embedded is not None and json.loads(embedded.group(1)) == checked


@pytest.mark.skipif(not _parses(_PENDING["explore"]), reason="explore (#791) is not merged yet")
def test_agent_flow_without_a_contract_uses_explore(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Step 2 without `archkeel.toml`: explore, then the same check; no rule means no PASS."""
    from test_architecture_demo import _prepare_repo

    contract_files = ("archkeel.toml", "archkeel-tests.toml", "architecture-contract.json")
    root = _prepare_repo(tmp_path, dict.fromkeys(contract_files))
    assert main(["explore", "--root", str(root), "--output", str(tmp_path / "x"), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostics"][0]["kind"] == "scope_empty"
    scope = ["--source", "shop", "--namespace", "shop", "--output", str(tmp_path / "explore")]
    assert main(["explore", "--root", str(root), *scope, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["declared_rules"] == "UNKNOWN"
    snapshot = Path(result["artifact"])
    spec = _agent_spec(snapshot, _PLACE_ORDER[:2], [])
    spec["nodes"].append("COMP-APP")
    code, checked = _view("check", tmp_path, snapshot, spec, capsys)
    assert code == 0 and checked["steps"][1]["status"] == "proven"
    assert {node["id"]: node["status"] for node in checked["nodes"]}["COMP-APP"] == "declared"
