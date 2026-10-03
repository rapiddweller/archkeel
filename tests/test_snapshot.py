# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from __future__ import annotations

import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from archkeel.check.ports import ScanConfig
from archkeel.check.run import materialize_declarations
from archkeel.check.snapshot import SnapshotError, _materialize_archive, materialize_git_snapshot
from archkeel.ir.profiles import Language

ROOT = Path(__file__).parents[2]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _committed_repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "architecture@example.invalid")
    _git(root, "config", "user.name", "Architecture Test")
    _write(root / "example/__init__.py", "")
    _write(root / "example/tasks/sample.py", "value = 1\n")
    _write(root / "example/tasks/README.md", "not production Python\n")
    _write(root / "script/helper.py", "not_in_scope = True\n")
    _write(root / "pyproject.toml", '[project]\nrequires-python = ">=3.11"\n')
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "fixture")
    return root, _git(root, "rev-parse", "HEAD")


def _tar_with(member: tarfile.TarInfo, payload: bytes = b"") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as stream:
        if member.isfile():
            member.size = len(payload)
            stream.addfile(member, io.BytesIO(payload))
        else:
            stream.addfile(member)
    return buffer.getvalue()


def test_git_snapshot_contains_only_tracked_production_python(tmp_path: Path) -> None:
    root, git_head = _committed_repository(tmp_path)
    _write(root / "example/untracked.py", "must_not_leak = True\n")

    with materialize_git_snapshot(root, git_head, roots=("example",)) as snapshot:
        assert snapshot.git_head == git_head
        assert sorted(
            path.relative_to(snapshot.root).as_posix() for path in snapshot.root.rglob("*")
        ) == [
            "example",
            "example/__init__.py",
            "example/tasks",
            "example/tasks/sample.py",
            "pyproject.toml",
        ]
        assert not (snapshot.root / "example/untracked.py").exists()


@pytest.mark.parametrize("tsconfig", ["src/app/tsconfig.json", "config/compiler.opts"])
def test_typescript_snapshot_includes_tracked_resolver_closure_outside_roots(
    tmp_path: Path,
    tsconfig: str,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "architecture@example.invalid")
    _git(root, "config", "user.name", "Architecture")
    for path, value in {
        "src/app/main.ts": "import '../shared/helper.js';\n",
        "src/shared/helper.mts": "export const helper = 1;\n",
        "types/shared.d.ts": "export declare const value: string;\n",
        "package.json": '{"type":"module"}\n',
        tsconfig: '{"compilerOptions":{}}\n',
        "src/app/not-source.txt": "ignored\n",
    }.items():
        _write(root / path, value)
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "TypeScript source")
    revision = _git(root, "rev-parse", "HEAD")
    _write(root / "node_modules/pkg/index.ts", "untracked\n")

    with materialize_git_snapshot(
        root, revision, roots=("src/app",), language="typescript", tsconfig=tsconfig
    ) as snapshot:
        paths = {
            path.relative_to(snapshot.root).as_posix()
            for path in snapshot.root.rglob("*")
            if path.is_file()
        }
        assert paths == {
            "src/app/main.ts",
            "src/shared/helper.mts",
            "types/shared.d.ts",
            "package.json",
            tsconfig,
        }
        assert not (snapshot.root / "node_modules/pkg/index.ts").exists()


def test_dart_snapshot_binds_pubspec_and_scoped_dart_sources(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "architecture@example.invalid")
    _git(root, "config", "user.name", "Architecture")
    _write(root / "pubspec.yaml", "name: package_name\n")
    _write(root / "lib/main.dart", "void main() {}\n")
    _write(root / "lib/readme.md", "ignored\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "Dart source")
    revision = _git(root, "rev-parse", "HEAD")

    with materialize_git_snapshot(root, revision, roots=("lib",), language="dart") as snapshot:
        assert (snapshot.root / "pubspec.yaml").is_file()
        assert (snapshot.root / "lib/main.dart").is_file()
        assert not (snapshot.root / "lib/readme.md").exists()


def test_git_snapshot_binds_pyproject_to_each_revision(tmp_path: Path) -> None:
    root, first = _committed_repository(tmp_path)
    _write(root / "pyproject.toml", '[project]\nrequires-python = ">=3.12"\n')
    _git(root, "add", "pyproject.toml")
    _git(root, "commit", "-q", "-m", "new runtime")
    second = _git(root, "rev-parse", "HEAD")

    with materialize_git_snapshot(root, first, roots=("example",)) as snapshot:
        assert snapshot.root.joinpath("pyproject.toml").read_text() == (
            '[project]\nrequires-python = ">=3.11"\n'
        )
    with materialize_git_snapshot(root, second, roots=("example",)) as snapshot:
        assert snapshot.root.joinpath("pyproject.toml").read_text() == (
            '[project]\nrequires-python = ">=3.12"\n'
        )


def test_git_snapshot_allows_missing_pyproject(tmp_path: Path) -> None:
    root, _ = _committed_repository(tmp_path)
    _git(root, "rm", "-q", "pyproject.toml")
    _git(root, "commit", "-q", "-m", "remove metadata")
    git_head = _git(root, "rev-parse", "HEAD")

    with materialize_git_snapshot(root, git_head, roots=("example",)) as snapshot:
        assert not snapshot.root.joinpath("pyproject.toml").exists()


@pytest.mark.parametrize(
    ("language", "source", "metadata"),
    [
        ("python", "src/main.py", "pyproject.toml"),
        ("dart", "src/main.dart", "pubspec.yaml"),
        ("typescript", "src/main.ts", "tsconfig.json"),
    ],
)
@pytest.mark.parametrize("attribute", ["export-ignore", "export-subst"])
def test_snapshot_preserves_selected_git_blobs_despite_export_attributes(
    tmp_path: Path, language: Language, source: str, metadata: str, attribute: str
) -> None:
    root, _ = _committed_repository(tmp_path)
    _git(root, "config", "core.autocrlf", "false")
    payload = b"$Format:%H$\r\nrevision bytes\n"
    for path in (source, metadata):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    _write(root / ".gitattributes", f"{source} {attribute}\n{metadata} {attribute}\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "export attributes")
    revision = _git(root, "rev-parse", "HEAD")
    (root / source).write_bytes(b"worktree must not leak\n")
    (root / metadata).write_bytes(b"worktree must not leak\n")

    with materialize_git_snapshot(root, revision, roots=("src",), language=language) as snapshot:
        assert (snapshot.root / source).read_bytes() == payload
        assert (snapshot.root / metadata).read_bytes() == payload


def test_export_ignore_cannot_hide_an_unresolved_dart_import(tmp_path: Path) -> None:
    from archkeel.analyzer import observe
    from archkeel.check.run import observe_revision

    root, _ = _committed_repository(tmp_path)
    _write(root / "lib/main.dart", "void main() {}\n")
    _write(root / "lib/hidden.dart", "import 'missing.dart';\n")
    _write(root / "pubspec.yaml", "name: example\n")
    _write(root / ".gitattributes", "lib/hidden.dart export-ignore\n")
    _write(root / "contract.json", '{"schema_version":"2.1.0","components":[],"rules":[]}')
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "hidden unresolved import")
    revision = _git(root, "rev-parse", "HEAD")
    config = ScanConfig(("lib",), "example", "contract.json", "0" * 64, language="dart")

    result = observe_revision(observe, root, revision, config, declared_at=revision)

    assert result.exit_code == 2
    assert result.coverage.status == "FAIL"


@pytest.mark.parametrize(
    ("language", "suffix"), [("python", ".py"), ("dart", ".dart"), ("typescript", ".ts")]
)
def test_snapshot_rejects_selected_git_symlink(
    tmp_path: Path, language: Language, suffix: str
) -> None:
    root, _ = _committed_repository(tmp_path)
    (root / "src").mkdir()
    (root / f"src/link{suffix}").symlink_to("../pyproject.toml")
    _write(root / f"src/main{suffix}", "source\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "source symlink")

    with (
        pytest.raises(SnapshotError),
        materialize_git_snapshot(root, "HEAD", roots=("src",), language=language),
    ):
        pass


@pytest.mark.parametrize(
    ("language", "raw_path", "selected"),
    [
        ("python", b"docs/bad\xff.py", False),
        ("python", b"example/bad\xff.py", True),
        ("dart", b"docs/bad\xff.dart", False),
        ("dart", b"example/bad\xff.dart", True),
        ("typescript", b"docs/bad\xff.txt", False),
        ("typescript", b"docs/bad\xff.ts", True),
        ("typescript", b"docs/bad\xff.json", True),
        ("typescript", b"example/bad\xff.ts", True),
    ],
)
def test_snapshot_rejects_undecodable_paths_only_when_selected(
    tmp_path: Path,
    language: Language,
    raw_path: bytes,
    selected: bool,
) -> None:
    root, revision = _committed_repository(tmp_path)
    _write(root / "docs/README.md", "unrelated documentation\n")
    if language != "python":
        suffix = ".dart" if language == "dart" else ".ts"
        _write(root / f"example/source{suffix}", "// snapshot source\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "profile source")
    directory, filename = raw_path.rsplit(b"/", 1)
    entries = subprocess.check_output(
        ["git", "ls-tree", "-z", f"HEAD:{directory.decode()}"], cwd=root
    )
    blob = _git(root, "rev-parse", "HEAD:example/tasks/sample.py").encode()
    tree = subprocess.check_output(
        ["git", "mktree", "-z"],
        cwd=root,
        input=entries + b"100644 blob " + blob + b"\t" + filename + b"\0",
    ).strip()
    entries = subprocess.check_output(["git", "ls-tree", "-z", "HEAD"], cwd=root)
    entries = b"".join(
        entry + b"\0"
        for entry in entries.split(b"\0")
        if entry and entry.split(b"\t", 1)[1] != directory
    )
    tree = subprocess.check_output(
        ["git", "mktree", "-z"],
        cwd=root,
        input=entries + b"040000 tree " + tree + b"\t" + directory + b"\0",
    ).strip()
    revision = _git(root, "commit-tree", tree.decode(), "-p", "HEAD", "-m", "raw filename")
    if selected:
        with (
            pytest.raises(SnapshotError),
            materialize_git_snapshot(root, revision, roots=("example",), language=language),
        ):
            pass
    else:
        with materialize_git_snapshot(
            root, revision, roots=("example",), language=language
        ) as snapshot:
            source = "tasks/sample.py" if language == "python" else f"source{suffix}"
            expected = b"value = 1\n" if language == "python" else b"// snapshot source\n"
            assert (snapshot.root / "example" / source).read_bytes() == expected


def test_archive_with_only_metadata_has_no_scoped_python_sources(tmp_path: Path) -> None:
    metadata = tarfile.TarInfo("pyproject.toml")
    with pytest.raises(SnapshotError, match="no scoped Python sources"):
        _materialize_archive(
            _tar_with(metadata, b'[project]\nrequires-python = ">=3.11"\n'),
            tmp_path / "snapshot",
            roots=("example",),
        )


def test_git_snapshot_rejects_missing_revision(tmp_path: Path) -> None:
    root, _ = _committed_repository(tmp_path)

    with (
        pytest.raises(SnapshotError, match="cannot resolve Git revision"),
        materialize_git_snapshot(root, "f" * 40, roots=("example",)),
    ):
        pass


@pytest.mark.parametrize(
    "member",
    [
        tarfile.TarInfo("../example/escape.py"),
        tarfile.TarInfo("example/link.py"),
        tarfile.TarInfo("pyproject.toml"),
    ],
)
def test_git_snapshot_rejects_unsafe_or_linked_members(
    tmp_path: Path, member: tarfile.TarInfo
) -> None:
    if member.name.endswith("link.py") or member.name == "pyproject.toml":
        member.type = tarfile.SYMTYPE
        member.linkname = "target.py"

    with pytest.raises(SnapshotError, match="unsafe|unsupported"):
        _materialize_archive(
            _tar_with(member, b"value = 1\n"), tmp_path / "snapshot", roots=("example",)
        )


def test_declaration_snapshot_carries_the_contracts_an_inside_names(tmp_path: Path) -> None:
    """AD-36: without the inside contract, check observes one level and the lock names two."""
    root, _ = _committed_repository(tmp_path)
    _write(
        root / "architecture-contract.json",
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    {
                        "id": "COMP-TASKS",
                        "label": "tasks",
                        "role": "component",
                        "packages": ["example.tasks"],
                        "inside": "example/tasks/architecture-contract.json",
                        "responsibilities": ["Hold the sample task."],
                        "forbidden_responsibilities": ["Everything else."],
                        "provenance": ["example/tasks/README.md"],
                    }
                ],
                "rules": [],
            }
        ),
    )
    _write(
        root / "example/tasks/architecture-contract.json",
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    {
                        "id": "COMP-GENERATE",
                        "label": "generate",
                        "role": "component",
                        "packages": ["example.tasks.generate"],
                        "inside": "example/tasks/deep.json",
                        "responsibilities": [],
                        "forbidden_responsibilities": [],
                        "provenance": ["example/tasks/README.md"],
                    }
                ],
                "rules": [],
            }
        ),
    )
    _write(
        root / "example/tasks/deep.json",
        '{"schema_version": "2.1.0", "components": [], "rules": []}',
    )
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "declare an inside")
    commit = _git(root, "rev-parse", "HEAD")

    destination = tmp_path / "declarations"
    materialize_declarations(
        root,
        commit,
        ScanConfig(("example",), "example", "architecture-contract.json", "0" * 64),
        destination,
    )

    assert (destination / "example/tasks/architecture-contract.json").is_file()
    assert (destination / "example/tasks/deep.json").is_file()
    assert (destination / "example/tasks/README.md").is_file()
