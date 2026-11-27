# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check the rolling main build publication."""

import copy
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import unquote

import pytest

from tools import publish_main_build as build

REPO = "rapiddweller/archkeel"
FOREIGN = "notes.pdf"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _wheel(path: Path, sha: str, tag: str, payload: bytes, version: str | None = None) -> None:
    version = version or f"4.0.2.dev{sha[0]}+g{sha[:9]}"
    with zipfile.ZipFile(path / f"archkeel-{version}-{tag}.whl", "w") as archive:
        archive.writestr(f"archkeel-{version}.dist-info/METADATA", f"Version: {version}\n")
        archive.writestr("payload", payload)


class Hub:
    """The release API of GitHub as far as the publisher uses it. It can fail on request."""

    def __init__(self, root: Path, first: str) -> None:
        self.root = root
        self.commits = [first]
        self.assets: dict[int, dict[str, str]] = {}
        self.next_id = 1
        self.body = f"Commit: {first}\n"
        self.tag = first
        self.mutations = 0
        self.fail_at: int | None = None
        self.corrupt_next_upload = False
        self.partial_upload = False
        self.page_size = 100
        self.calls: list[tuple[str, ...]] = []
        for tag in sorted(build.TAGS):
            self._add(
                f"archkeel-4.0.2.dev{first[0]}+g{first[:9]}-{tag}.whl", b"old " + tag.encode()
            )
        self._add(build.SUMS, b"old sums")
        self._add(FOREIGN, b"not ours")

    def _add(
        self, name: str, data: bytes, digest: str | None = None, state: str = "uploaded"
    ) -> None:
        digest = digest or "sha256:" + hashlib.sha256(data).hexdigest()
        self.assets[self.next_id] = {
            "name": name,
            "digest": digest,
            "state": state,
            "data": data.hex(),
        }
        self.next_id += 1

    def names(self) -> dict[str, str]:
        return {item["name"]: item["digest"] for item in self.assets.values()}

    def _find(self, path: str) -> int:
        return int(path.rsplit("/", 1)[1].split("?")[0])

    def _mutate(self, upload: Path | None = None) -> None:
        self.mutations += 1
        if self.fail_at == self.mutations:
            if upload is not None and self.partial_upload:
                self.assets[self.next_id] = {
                    "name": upload.name,
                    "digest": None,
                    "state": "starter",
                    "data": "",
                }
                self.next_id += 1
            raise RuntimeError("injected failure")

    def command(self, *args: str) -> str:
        self.calls.append(args)
        match args[:2]:
            case ("git", "show"):
                return "2026-11-18T00:00:00Z"
            case ("gh", "api") if args[2] == "-X":
                self._mutate()
                if args[3] == "DELETE":
                    del self.assets[self._find(args[4])]
                elif "git/refs" in args[4]:
                    self.tag = next(a for a in args if a.startswith("sha=")).removeprefix("sha=")
                else:
                    self.assets[self._find(args[4])]["name"] = args[6].removeprefix("name=")
                return ""
            case ("gh", "api") if "--paginate" in args and "/assets" in args[-1]:
                items = [{"id": key, **item} for key, item in self.assets.items()]
                size = self.page_size
                return json.dumps([items[i : i + size] for i in range(0, len(items), size)])
            case ("gh", "api"):
                return json.dumps(
                    {
                        "id": 7,
                        "draft": False,
                        "prerelease": True,
                        "body": self.body,
                        "tag_name": "main-build",
                    }
                )
            case ("gh", "release") if args[2] == "upload":
                path = Path(args[4])
                self._mutate(path)
                if path.name in self.names():
                    raise RuntimeError("asset already exists")
                bad = "sha256:" + "0" * 64 if self.corrupt_next_upload else None
                self.corrupt_next_upload = False
                self._add(path.name, path.read_bytes(), bad)
            case ("gh", "release") if args[2] == "edit":
                self._mutate()
                self.body = Path(args[args.index("--notes-file") + 1]).read_text()
        return ""


@pytest.fixture
def hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Hub:
    _git(tmp_path, "init", "-q")
    shas = []
    for number in range(4):
        _git(tmp_path, "commit", "-q", "--allow-empty", "-m", str(number))
        shas.append(_git(tmp_path, "rev-parse", "HEAD"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    state = Hub(tmp_path, shas[0])
    state.commits = shas
    monkeypatch.setattr(build, "command", state.command)
    return state


def _publish(
    hub: Hub, monkeypatch: pytest.MonkeyPatch, number: int, payload: bytes = b"new"
) -> None:
    sha = hub.commits[number]
    dist = hub.root / "dist"
    dist.mkdir(exist_ok=True)
    for old in dist.glob("*.whl"):
        old.unlink()
    for tag in build.TAGS:
        _wheel(dist, sha, tag, payload + tag.encode())
    monkeypatch.setenv("GITHUB_SHA", sha)
    build.main()


def _wheels(hub: Hub) -> set[str]:
    return {name for name in hub.names() if name.endswith(".whl")}


def _build_of(hub: Hub, number: int) -> set[str]:
    sha = hub.commits[number]
    return {n for n in hub.names() if n.startswith(f"archkeel-4.0.2.dev{sha[0]}+g{sha[:9]}")}


def _assert_clean(hub: Hub, number: int, kept: tuple[int, ...] = (0,)) -> None:
    """`number` is the newest build; `kept` are the older builds that stay public (#2183)."""
    sha = hub.commits[number]
    names = hub.names()
    assert _wheels(hub) == set().union(*(_build_of(hub, n) for n in (number, *kept)))
    assert len(_build_of(hub, number)) == 6
    assert set(names) == {*_wheels(hub), build.SUMS, FOREIGN}
    sums = next(i for i in hub.assets.values() if i["name"] == build.SUMS)
    listed = dict(
        line.split("  ")[::-1] for line in bytes.fromhex(sums["data"]).decode().splitlines()
    )
    assert {n: "sha256:" + d for n, d in listed.items()} == {n: names[n] for n in _wheels(hub)}
    assert hub.body.count(f"Commit: {sha}") == 1
    assert hub.tag == sha
    assert build.LINKS in hub.body and re.search(r"^Commit: [0-9a-f]{40}$", hub.body, re.M)


def test_a_new_build_adds_its_wheels_and_keeps_the_older_ones(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _build_of(hub, 0)
    urls = hub.names()
    _publish(hub, monkeypatch, 1)
    _assert_clean(hub, 1, (0,))
    _publish(hub, monkeypatch, 2)
    _assert_clean(hub, 2, (0, 1))
    assert first <= set(hub.names())
    # A wheel that was public keeps its name and its bytes (the URL of a pin does not change).
    assert all(hub.names()[name] == digest for name, digest in urls.items() if name in first)
    assert hub.names()[FOREIGN].startswith("sha256:")
    assert not any(
        c[:3] in (("gh", "release", "create"), ("gh", "release", "delete")) for c in hub.calls
    )


def test_the_builds_past_the_newest_keep_are_pruned(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The Hub starts with build 0. With KEEP 3 the third new build drops build 0 and keeps the rest.
    monkeypatch.setattr(build, "KEEP", 3)
    _publish(hub, monkeypatch, 1)
    _assert_clean(hub, 1, (0,))
    _publish(hub, monkeypatch, 2)
    _assert_clean(hub, 2, (0, 1))
    _publish(hub, monkeypatch, 3)
    _assert_clean(hub, 3, (1, 2))
    assert hub.names()[FOREIGN].startswith("sha256:")
    assert not any(
        c[:3] in (("gh", "release", "create"), ("gh", "release", "delete")) for c in hub.calls
    )


def test_the_inventory_reads_every_page(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    # The real API gives at most 100 assets in a page. A page of 7 needs many pages for four builds.
    hub.page_size = 7
    _publish(hub, monkeypatch, 1)
    _publish(hub, monkeypatch, 2)
    _publish(hub, monkeypatch, 3)
    _assert_clean(hub, 3, (0, 1, 2))
    assert sum(1 for c in hub.calls if "--paginate" in c) > 3


def test_a_rerun_changes_nothing_public(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    _publish(hub, monkeypatch, 1)
    before = hub.names()
    hub.calls.clear()
    _publish(hub, monkeypatch, 1, payload=b"rebuilt with other bytes")
    assert hub.names() == before
    assert not any(c[:3] == ("gh", "release", "upload") for c in hub.calls)
    assert not any(c[:4] == ("gh", "api", "-X", "DELETE") for c in hub.calls)
    _assert_clean(hub, 1)


def test_an_older_run_does_not_replace_a_newer_build(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(hub, monkeypatch, 2)
    before = (hub.names(), hub.body, hub.tag)
    hub.mutations = 0
    _publish(hub, monkeypatch, 1)
    assert (hub.names(), hub.body, hub.tag) == before
    assert hub.mutations == 0


@pytest.mark.parametrize("partial", [False, True])
def test_a_failure_at_any_step_keeps_a_usable_set_and_a_rerun_recovers(
    hub: Hub, monkeypatch: pytest.MonkeyPatch, partial: bool
) -> None:
    _publish(hub, monkeypatch, 1)
    saved = copy.deepcopy((hub.assets, hub.next_id, hub.body, hub.tag))
    old = _wheels(hub)
    hub.mutations = 0
    _publish(hub, monkeypatch, 2)
    steps = hub.mutations
    assert steps > 10
    hub.partial_upload = partial
    for step in range(1, steps + 1):
        hub.assets, hub.next_id, hub.body, hub.tag = copy.deepcopy(saved)
        hub.mutations, hub.fail_at = 0, step
        with pytest.raises(RuntimeError, match="injected"):
            _publish(hub, monkeypatch, 2)
        hub.fail_at = None
        names = hub.names()
        new = {n for n in names if f"+g{hub.commits[2][:9]}" in n and n.endswith(".whl")}
        # The old set stays whole until the new set is public and checked.
        assert old <= set(names) or len(new) == 6
        assert build.SUMS in names or build.SUMS + build.PREVIOUS in names
        assert {
            t for t in build.TAGS for n in _wheels(hub) if n.endswith(f"-{t}.whl")
        } == build.TAGS
        assert FOREIGN in names
        _publish(hub, monkeypatch, 2)
        _assert_clean(hub, 2, (0, 1))


@pytest.mark.parametrize("partial", [False, True])
def test_an_older_run_does_not_clear_away_a_newer_stopped_promotion(
    hub: Hub, monkeypatch: pytest.MonkeyPatch, partial: bool
) -> None:
    _publish(hub, monkeypatch, 1)
    saved = copy.deepcopy((hub.assets, hub.next_id, hub.body, hub.tag))
    hub.mutations = 0
    _publish(hub, monkeypatch, 3)
    steps = hub.mutations
    hub.partial_upload = partial
    newer = f"+g{hub.commits[3][:9]}"
    shown = set()
    for step in range(1, steps + 1):
        hub.assets, hub.next_id, hub.body, hub.tag = copy.deepcopy(saved)
        hub.mutations, hub.fail_at = 0, step
        with pytest.raises(RuntimeError, match="injected"):
            _publish(hub, monkeypatch, 3)
        hub.fail_at = None
        if any(newer in name for name in hub.names()):
            # The notes may still name commit 1 while wheels of commit 3 are public.
            public = any(newer in n and n.endswith(".whl") for n in hub.names())
            shown.add((public, f"Commit: {hub.commits[1]}" in hub.body))
            before = (hub.names(), hub.body, hub.tag)
            hub.mutations = 0
            _publish(hub, monkeypatch, 2)
            assert (hub.names(), hub.body, hub.tag) == before
            assert hub.mutations == 0
        _publish(hub, monkeypatch, 3)
        _assert_clean(hub, 3, (0, 1))
    # The cases include public newer wheels under old notes, and only staged newer wheels.
    assert {(True, True), (False, True)} <= shown


def test_the_asset_names_follow_the_live_release_api() -> None:
    # Live (GET only, 2026-11-18): the API name keeps "+"; the download link has "%2B" and the page
    # lists the same names after unquoting; the digest is "sha256:<hex>"; the state is "uploaded".
    live = "archkeel-4.0.2.dev818+g75037b1f7-py3-none-manylinux_2_17_x86_64.whl"
    assert build.OWN.fullmatch(live) and build.OWN.fullmatch(live + build.STAGING)
    assert build.OWN.fullmatch(build.SUMS) and not build.OWN.fullmatch(FOREIGN)
    assert unquote(f"https://x/main-build/{live.replace('+', '%2B')}".rsplit("/", 1)[1]) == live
    assert live.split("-")[1] == "4.0.2.dev818+g75037b1f7"
    notes = "Development build, not a release.\n\nCommit: " + "7" * 40 + "\nDate: 2026-11-18\n"
    assert re.search(r"^Commit: ([0-9a-f]{40})\s*$", notes.replace("\n", "\r\n"), re.MULTILINE)


def test_a_damaged_upload_stops_before_the_first_public_change(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub.corrupt_next_upload = True
    old = hub.names()
    with pytest.raises(ValueError, match="nothing was promoted"):
        _publish(hub, monkeypatch, 1)
    public = {n: d for n, d in hub.names().items() if not n.endswith(build.STAGING)}
    assert public == old
    _publish(hub, monkeypatch, 1)
    _assert_clean(hub, 1)


@pytest.mark.parametrize("damage", ["missing", "other commit", "other version"])
def test_a_bad_candidate_is_refused_before_any_call(
    hub: Hub, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    sha = hub.commits[1]
    dist = hub.root / "dist"
    dist.mkdir()
    for tag in sorted(build.TAGS)[: 5 if damage == "missing" else 6]:
        version = f"4.0.2.dev1+g{'f' * 9}" if damage == "other commit" else None
        _wheel(dist, sha, tag, b"x", version)
    if damage == "other version":
        wheel = next(dist.glob("*.whl"))
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("archkeel-9.dist-info/METADATA", "Version: 9\n")
    monkeypatch.setenv("GITHUB_SHA", sha)
    with pytest.raises(ValueError):
        build.main()
    assert hub.calls == []


def test_the_release_must_stay_a_published_pre_release(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = hub.command

    def latest(*args: str) -> str:
        text = original(*args)
        return (
            text.replace('"prerelease": true', '"prerelease": false')
            if "releases/tags" in args[-1]
            else text
        )

    monkeypatch.setattr(build, "command", latest)
    with pytest.raises(ValueError, match="pre-release"):
        _publish(hub, monkeypatch, 1)
    assert hub.mutations == 0
