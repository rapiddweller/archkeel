# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Export and verify the installable plugin from the canonical repository files."""

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _plugin_files(
    expected_version: str | None, release_version: str | None = None
) -> dict[str, bytes]:
    metadata = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    version = metadata["version"]
    if (
        metadata["name"] != "archkeel"
        or claude["name"] != "archkeel"
        or not isinstance(version, str)
        or not version
        or claude["version"] != version
    ):
        raise ValueError("Plugin manifests must share the expected ArchKeel release version")
    if release_version is not None:
        if not release_version:
            raise ValueError("Plugin release version must not be empty")
        metadata["version"] = claude["version"] = release_version
    if expected_version is not None and metadata["version"] != expected_version:
        raise ValueError("Plugin manifests must share the expected ArchKeel release version")
    interface = metadata["extensions"]["com.openai"]["interface"]
    readme = (
        f"# {interface['displayName']}\n\n{metadata['description']}\n\n"
        f"{interface['longDescription']}\n"
    ).encode()
    return {
        "plugin.json": (
            (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode()
            if release_version is not None
            else (ROOT / "plugin.json").read_bytes()
        ),
        ".claude-plugin/plugin.json": (
            (json.dumps(claude, indent=2, ensure_ascii=False) + "\n").encode()
            if release_version is not None
            else (ROOT / ".claude-plugin/plugin.json").read_bytes()
        ),
        "skills/archkeel/SKILL.md": (ROOT / "skills/archkeel/SKILL.md").read_bytes(),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
        "README.md": readme,
        "docs/assets/archkeel-mark.svg": (
            ROOT / "src/archkeel/render/assets/archkeel-mark.svg"
        ).read_bytes(),
    }


def _checksum(archive: Path) -> str:
    return f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n"


def _check_bundle(archive: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = [entry.filename for entry in entries if not entry.is_dir()]
        directories = {
            parent.as_posix() + "/"
            for name in files
            for parent in Path(name).parents
            if parent != Path(".")
        }
        if (
            len(names) != len(set(names))
            or set(names) != set(files)
            or any(entry.filename not in directories for entry in entries if entry.is_dir())
        ):
            raise ValueError("Plugin ZIP must contain exactly the distributable files")
        for entry in entries:
            kind = stat.S_IFMT(entry.external_attr >> 16)
            expected_kind = stat.S_IFDIR if entry.is_dir() else stat.S_IFREG
            if (
                kind not in (0, expected_kind)
                or not entry.is_dir()
                and entry.external_attr & 0x10
                or entry.is_dir()
                and kind != stat.S_IFDIR
                and not entry.external_attr & 0x10
            ):
                raise ValueError(f"Plugin ZIP has non-regular entry metadata: {entry.filename}")
        for name, expected in files.items():
            if bundle.read(name) != expected:
                raise ValueError(f"Plugin ZIP differs from canonical source: {name}")
    if Path(str(archive) + ".sha256").read_text(encoding="utf-8") != _checksum(archive):
        raise ValueError("Plugin ZIP checksum does not match")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New plugin directory, or ZIP with --check.")
    parser.add_argument("--expected-version", help="Required version in both plugin manifests.")
    parser.add_argument(
        "--release-version", help="Stamp both exported manifests; keep source unchanged."
    )
    parser.add_argument("--check", action="store_true", help="Verify an existing ZIP and checksum.")
    args = parser.parse_args()
    target = args.output.resolve()
    files = _plugin_files(args.expected_version, args.release_version)
    if args.check:
        _check_bundle(target, files)
        print(target)
        return
    archive = Path(str(target) + ".zip")
    checksum = Path(str(archive) + ".sha256")
    if archive.exists() or checksum.exists():
        parser.error(f"ZIP or checksum already exists: {archive}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    # Fixed metadata makes a retry of the same release produce identical asset bytes.
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            bundle.writestr(entry, files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    checksum.write_text(_checksum(archive), encoding="utf-8")
    _check_bundle(archive, files)
    print(target)


if __name__ == "__main__":
    main()
