# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publication cannot precede verified draft bytes or survive failed PyPI upload."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tools import publish_release


class Remote:
    def __init__(self, root):
        self.commit = "a" * 40
        self.tag_commit = self.commit
        self.release = None
        self.assets = {}
        self.events = []
        self.fail = None
        self.corrupt = False
        self.root = root
        self.move_tag_after_upload = False
        self.tag_ref = None
        self.tag_objects = {}

    def run(self, args, *, check, stdout=None):
        self.events.append(tuple(args))
        if self.fail == args[0] or self.fail == tuple(args[:3]):
            raise subprocess.CalledProcessError(1, args)
        if args[0] == "git":
            result = self.commit.encode()
        elif args[:2] == ["uv", "publish"]:
            assert self.release["draft"]
            local = {
                path.name
                for folder in ("dist", "plugin")
                for path in self.root.joinpath(folder).iterdir()
            }
            assert set(self.assets) == local
            downloads = [e for e in self.events if "Accept: application/octet-stream" in e]
            assert len(downloads) >= len(local)
            result = b""
        elif args[1:3] == ("release", "create"):
            note_file = Path(args[args.index("--notes-file") + 1])
            self.release = {
                "id": 7,
                "tag_name": "5.0.0",
                "draft": True,
                "target_commitish": self.commit,
                "body": note_file.read_text(),
                "assets": [],
            }
            result = b""
        elif args[1:3] == ("release", "upload"):
            assert "--clobber" not in args
            for value in args[4 : args.index("--repo")]:
                path = Path(value)
                assert path.name not in self.assets
                asset_id = len(self.assets) + 1
                self.assets[path.name] = path.read_bytes()
                self.release["assets"].append({"id": asset_id, "name": path.name})
            if self.move_tag_after_upload:
                self.tag_commit = "b" * 40
            result = b""
        elif args[1] == "api":
            endpoint = args[2]
            if "/git/ref/tags/" in endpoint:
                result = {
                    "ref": "refs/tags/5.0.0",
                    "object": self.tag_ref or {"type": "commit", "sha": self.tag_commit},
                }
            elif "/git/tags/" in endpoint:
                result = {"object": self.tag_objects[endpoint.rsplit("/", 1)[1]]}
            elif endpoint.endswith("releases?per_page=100"):
                result = [[self.release] if self.release else []]
            elif "/releases/assets/" in endpoint:
                asset = next(
                    a for a in self.release["assets"] if str(a["id"]) == endpoint.rsplit("/", 1)[1]
                )
                return subprocess.CompletedProcess(
                    args, 0, b"corrupt" if self.corrupt else self.assets[asset["name"]]
                )
            else:
                assert endpoint.endswith("releases/7")
                if "draft=false" in args:
                    assert any(e[0] == "uv" for e in self.events)
                    self.release["draft"] = False
                else:
                    self.release["body"] = next(a[5:] for a in args if a.startswith("body="))
                result = self.release
            result = json.dumps(result).encode()
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, result)


@pytest.fixture
def release(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    plugin = tmp_path / "plugin"
    dist.mkdir()
    plugin.mkdir()
    (dist / "archkeel-5.0.0-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "archkeel-5.0.0.tar.gz").write_bytes(b"sdist")
    archive = plugin / "archkeel-plugin-5.0.0.zip"
    archive.write_bytes(b"plugin")
    archive.with_suffix(".zip.sha256").write_text(
        hashlib.sha256(b"plugin").hexdigest() + f"  {archive.name}\n"
    )
    notes = tmp_path / "notes.md"
    notes.write_text(
        "# ArchKeel 5.0.0 — Release\n\n## Highlights\n\nNew.\n\n# ArchKeel 4.0.1\nOld.\n"
    )
    remote = Remote(tmp_path)
    monkeypatch.setattr(publish_release.subprocess, "run", remote.run)
    return remote, dist, plugin, notes


def publish(release):
    remote, dist, plugin, notes = release
    publish_release.publish("owner/repo", "5.0.0", remote.commit, dist, plugin, notes)


def test_new_release_downloads_every_asset_before_pypi_and_publishes_same_draft(release):
    publish(release)
    remote = release[0]
    assert not remote.release["draft"]
    assert remote.release["id"] == 7
    assert "4.0.1" not in remote.release["body"]
    assert "## Highlights" in remote.release["body"]
    assert len([e for e in remote.events if e[1:3] == ("release", "create")]) == 1
    assert len([e for e in remote.events if "Accept: application/octet-stream" in e]) == 8


@pytest.mark.parametrize(
    "failed",
    ["uv", ("gh", "release", "upload"), ("gh", "api", "repos/owner/repo/releases/assets/1")],
)
def test_failure_keeps_draft_and_stops_later_publication(release, failed):
    remote = release[0]
    remote.fail = failed
    with pytest.raises(subprocess.CalledProcessError):
        publish(release)
    assert remote.release["draft"]
    assert not any("draft=false" in e for e in remote.events)
    if failed != "uv":
        assert not any(e[0] == "uv" for e in remote.events)


def test_corrupt_download_blocks_pypi(release):
    remote = release[0]
    remote.corrupt = True
    with pytest.raises(ValueError, match="downloaded release asset differs"):
        publish(release)
    assert not any(e[0] == "uv" for e in remote.events)


def test_failed_pypi_rerun_reuses_draft_without_overwriting_assets(release):
    remote = release[0]
    remote.fail = "uv"
    with pytest.raises(subprocess.CalledProcessError):
        publish(release)
    remote.fail = None
    publish(release)
    assert not remote.release["draft"]
    assert len([e for e in remote.events if e[1:3] == ("release", "create")]) == 1
    assert len([e for e in remote.events if e[1:3] == ("release", "upload")]) == 1


@pytest.mark.parametrize("change", ["published", "commit", "unexpected", "bytes"])
def test_conflicting_existing_release_is_never_overwritten(release, change):
    remote = release[0]
    remote.fail = "uv"
    with pytest.raises(subprocess.CalledProcessError):
        publish(release)
    remote.fail = None
    if change == "published":
        remote.release["draft"] = False
    elif change == "commit":
        remote.release["target_commitish"] = "b" * 40
    elif change == "unexpected":
        remote.release["assets"].append({"id": 9, "name": "foreign.zip"})
    else:
        remote.assets[next(iter(remote.assets))] = b"different"
    remote.events.clear()
    with pytest.raises(ValueError):
        publish(release)
    assert not any(
        e[0] == "uv" or e[1:3] == ("release", "upload") or "draft=false" in e for e in remote.events
    )


@pytest.mark.parametrize("change", ["tag", "notes", "checksum", "missing"])
def test_invalid_inputs_fail_before_any_release_mutation(release, change):
    remote, dist, plugin, notes = release
    if change == "tag":
        remote.tag_commit = "b" * 40
    elif change == "notes":
        notes.write_text("# ArchKeel 4.0.1\n")
    elif change == "checksum":
        next(plugin.glob("*.sha256")).write_text("wrong\n")
    else:
        next(dist.glob("*.whl")).unlink()
    with pytest.raises(ValueError):
        publish(release)
    assert remote.release is None


def test_partially_uploaded_draft_resumes_without_replacing_existing_bytes(release):
    remote = release[0]
    remote.fail = "uv"
    with pytest.raises(subprocess.CalledProcessError):
        publish(release)
    kept = remote.release["assets"][:1]
    remote.release["assets"] = kept
    remote.assets = {kept[0]["name"]: remote.assets[kept[0]["name"]]}
    remote.fail = None
    remote.events.clear()
    publish(release)
    upload = next(e for e in remote.events if e[1:3] == ("release", "upload"))
    assert len(upload[4 : upload.index("--repo")]) == 3
    assert not remote.release["draft"]


def test_moved_tag_stops_before_pypi(release):
    remote = release[0]
    remote.move_tag_after_upload = True
    with pytest.raises(ValueError, match="tag does not name"):
        publish(release)
    assert not any(e[0] == "uv" for e in remote.events)


def test_release_inventory_failure_is_not_mistaken_for_missing_release(release):
    remote = release[0]
    remote.fail = ("gh", "api", "repos/owner/repo/releases?per_page=100")
    with pytest.raises(subprocess.CalledProcessError):
        publish(release)
    assert remote.release is None


@pytest.mark.parametrize(
    "directory,name", [("dist", "archkeel-4.0.1.tar.gz"), ("plugin", "foreign.zip")]
)
def test_unexpected_local_assets_stop_before_creating_a_draft(release, directory, name):
    remote, dist, plugin, _ = release
    ((dist if directory == "dist" else plugin) / name).write_bytes(b"foreign")
    with pytest.raises(ValueError):
        publish(release)
    assert remote.release is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", True),
        ("id", "7"),
        ("draft", "false"),
        ("tag_name", None),
        ("target_commitish", []),
        ("body", []),
        ("assets", {}),
        ("assets", [{"id": 1, "name": None}]),
        ("assets", [{"id": False, "name": "x"}]),
    ],
)
def test_malformed_release_metadata_blocks_publication(release, field, value):
    remote = release[0]
    remote.release = {
        "id": 7,
        "tag_name": "5.0.0",
        "target_commitish": remote.commit,
        "draft": True,
        "body": None,
        "assets": [],
    }
    remote.release[field] = value
    with pytest.raises(ValueError):
        publish(release)
    assert not any(
        e[0] == "uv" or e[1:3] in (("release", "create"), ("release", "upload")) or "PATCH" in e
        for e in remote.events
    )


def test_nested_annotated_tag_is_resolved_through_exact_git_objects(release):
    remote = release[0]
    remote.tag_ref = {"type": "tag", "sha": "c" * 40}
    remote.tag_objects = {
        "c" * 40: {"type": "tag", "sha": "d" * 40},
        "d" * 40: {"type": "commit", "sha": remote.commit},
    }
    publish(release)
    assert not remote.release["draft"]
    assert not any("/commits/" in e[2] for e in remote.events if e[:2] == ("gh", "api"))


@pytest.mark.parametrize(
    "kind,sha", [("tree", "a" * 40), ("commit", "not-a-sha"), ("tag", "c" * 40)]
)
def test_invalid_or_cyclic_tag_cannot_create_release(release, kind, sha):
    remote = release[0]
    remote.tag_ref = {"type": kind, "sha": sha}
    remote.tag_objects = {"c" * 40: {"type": "tag", "sha": "c" * 40}}
    with pytest.raises(ValueError):
        publish(release)
    assert remote.release is None


def test_release_body_uses_public_tag_links_and_omits_historical_separator(release):
    remote, _, _, notes = release
    notes.write_text(
        "# ArchKeel 5.0.0 — Release\n\n"
        "[guide](docs/reference.md#compatibility) and [web](https://example.org).\n"
        "\n---\n\n# ArchKeel 4.0.1\nHistorical.\n"
    )
    publish(release)
    assert remote.release["body"] == (
        "# ArchKeel 5.0.0 — Release\n\n"
        "[guide](https://github.com/owner/repo/blob/5.0.0/docs/reference.md#compatibility) "
        "and [web](https://example.org).\n"
    )


def test_plugin_upload_selects_only_archive_and_checksum_from_exporter_directory(tmp_path):
    import shutil

    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/release.yml").read_text()
    step = workflow.split("      - name: Upload plugin archive and checksum\n", 1)[1]
    upload = step.split("          path: |\n", 1)[1].split("          if-no-files-found:", 1)[0]
    output = tmp_path / "build/plugin-release"
    unpacked = output / "archkeel-plugin-5.0.0"
    unpacked.mkdir(parents=True)
    (unpacked / "manifest.json").write_text("{}")
    archive = output / "archkeel-plugin-5.0.0.zip"
    archive.write_bytes(b"plugin")
    checksum = archive.with_suffix(".zip.sha256")
    checksum.write_text(hashlib.sha256(b"plugin").hexdigest() + f"  {archive.name}\n")
    # Execute the workflow's actual upload patterns against the exporter's layout.
    selected = {path for line in upload.splitlines() for path in tmp_path.glob(line.strip())}
    assert selected == {archive, checksum}
    download = tmp_path / "download"
    download.mkdir()
    for path in selected:
        shutil.copyfile(path, download / path.name)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "archkeel-5.0.0-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "archkeel-5.0.0.tar.gz").write_bytes(b"sdist")
    _, assets = publish_release._assets(dist, download, "5.0.0")
    assert len(assets) == 4


PLATFORM_WHEELS = [f"archkeel-5.0.0-{tag}.whl" for tag in publish_release.PLATFORM_TAGS]


def test_the_platform_tags_are_the_six_targets_of_the_build_hook():
    """AD-317: the pinned build images give these tags; each one is a tag of the build hook."""
    hook = _hook()
    assert sorted(publish_release.PLATFORM_TAGS) == sorted(
        hook.wheel_tag(platform)
        for platform in (
            "macosx_14_0_x86_64",
            "macosx_15_0_arm64",
            "manylinux_2_17_x86_64",
            "manylinux_2_17_aarch64",
            "musllinux_1_2_x86_64",
            "win_amd64",
        )
    )


def test_a_release_with_every_platform_wheel_uploads_and_publishes_each_one(release):
    remote, dist, _, _ = release
    for name in PLATFORM_WHEELS:
        (dist / name).write_bytes(name.encode())
    publish(release)
    assert not remote.release["draft"]
    assert set(PLATFORM_WHEELS) <= set(remote.assets)
    (upload,) = [e for e in remote.events if e[:2] == ("uv", "publish")]
    assert sorted(Path(arg).name for arg in upload if arg.endswith((".whl", ".tar.gz"))) == sorted(
        ["archkeel-5.0.0-py3-none-any.whl", *PLATFORM_WHEELS, "archkeel-5.0.0.tar.gz"]
    )


@pytest.mark.parametrize(
    "names",
    [
        PLATFORM_WHEELS[:5],
        [*PLATFORM_WHEELS, "archkeel-5.0.0-py3-none-manylinux_2_28_x86_64.whl"],
        ["archkeel-5.0.0-cp311-cp311-win_amd64.whl"],
    ],
    ids=["one-missing", "unknown-tag", "abi-tag"],
)
def test_platform_wheels_are_all_six_targets_or_none(release, names):
    remote, dist, _, _ = release
    for name in names:
        (dist / name).write_bytes(name.encode())
    with pytest.raises(ValueError, match="none or all six platform wheels"):
        publish(release)
    assert remote.release is None


def test_a_release_without_the_pure_wheel_stops_before_any_mutation(release):
    remote, dist, _, _ = release
    (dist / "archkeel-5.0.0-py3-none-any.whl").unlink()
    for name in PLATFORM_WHEELS:
        (dist / name).write_bytes(name.encode())
    with pytest.raises(ValueError, match="pure wheel"):
        publish(release)
    assert remote.release is None


def _hook():
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "hatch_build", Path(__file__).parents[1] / "native/hatch_build.py"
    )
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
