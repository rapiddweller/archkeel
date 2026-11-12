# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the SDK support layer with Python on every pubspec of each Dart corpus (AD-385)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypedDict

from archkeel.analyzer.dart.collect import _Collection
from archkeel.analyzer.dart.resolve import Resolver
from archkeel.analyzer.dart.snapshot import (
    Snapshot,
    SnapshotError,
    _pubspec_metadata,
    read_snapshot,
)
from archkeel.ir.facts import RuntimeRequirementState

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dart_discovery_parity import (  # noqa: E402
    FIXTURES,
    ROOT,
    Corpus,
    build,
    demo_variants,
    request,
    same_error,
)
from dart_discovery_parity import (
    native as discovery_native,
)


class Input(TypedDict):
    state: str
    constraint: str | None


@dataclass
class Result:
    name: str
    files: int = 0
    equal: int = 0
    stricter: int = 0
    different: int = 0


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def python(item: Input) -> dict[str, Any]:
    snapshot = Snapshot(
        (), "shop", item["constraint"], RuntimeRequirementState(item["state"]), (), (), (".",)
    )
    collection = _Collection(
        request(Corpus("sdk", ROOT, (".",), "shop")), snapshot, {}, Resolver(snapshot, {})
    )
    collection._sdk_constraints()
    return {
        "sdk_supported": collection.sdk_supported,
        "gaps": [value for _, value in sorted(collection.gaps.items())],
    }


def native(binary: Path, items: Sequence[Input]) -> list[dict[str, Any]]:
    text = "".join(canonical(item) + "\n" for item in items)
    run = subprocess.run(
        [str(binary), "--dump-sdk"],
        input=text,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    rows = [json.loads(line) for line in run.stdout.split("\n") if line]
    if len(rows) != len(items):
        raise AssertionError("the SDK dump dropped or added a result")
    return rows


def payload(row: dict[str, Any]) -> dict[str, Any]:
    return {"sdk_supported": row["sdk_supported"], "gaps": row["gaps"]}


def compare(binary: Path, name: str, raw: Sequence[bytes]) -> Result:
    inputs: list[Input] = []
    for data in raw:
        _, constraint, state = _pubspec_metadata(data)
        inputs.append({"state": state.value, "constraint": constraint})
    result = Result(name, len(inputs))
    for item, row in zip(inputs, native(binary, inputs), strict=True):
        messages = [gap["data"]["message"] for gap in row["gaps"]]
        stopped = any(
            "SdkConstraintWorkLimit" in message or "SdkConstraintDigitLimit" in message
            for message in messages
        )
        if stopped and row["sdk_supported"] is False and len(messages) == 1:
            result.stricter += 1
        elif canonical(payload(row)) == canonical(python(item)):
            result.equal += 1
        else:
            result.different += 1
    return result


def hostile() -> list[bytes]:
    constraints = [
        "",
        "any",
        "3.12",
        "^3.12",
        "^3.13",
        "^2.11",
        "^2.12",
        "^0",
        "^0.0.9",
        "^0.9",
        ">=3 <4",
        ">=3<=3",
        ">3<=3",
        "<3",
        ">=3,",
        "^3 <4",
        "=3.12.4",
        "^03.012",
        ">=٣.١٢",
        "=３.１２",
        ">=3.12-dev+build",
        "^3.12-",
        "^3.12+",
        "^3.12.0.0",
        "\u001c>=3.12\u2003<4",
        ">=3 || <4",
        "^3.12+...",
        ">=2.12 <99",
        ">2.11 <4",
        ">=3.12 <3.12",
        ">=3.12 <=3.12",
        "=3.12\x00",
        "^" + "0" * 4301 + "3.12",
        ">=3 " * 200_000,
    ]
    raw = [f"name: shop\nenvironment:\n  sdk: '{value}'\n".encode() for value in constraints]
    raw += [
        b"",
        b"name: shop\n",
        b"\xff",
        b"\xef\xbb\xbfname: shop\n",
        b"name: shop\nenvironment: {}\n",
        b"name: shop\nenvironment:\n  sdk: [3]\n",
        b"name: shop\nenvironment:\n  sdk: ^3\n  sdk: ^4\n",
        b"name: shop\nenvironment:\n\tsdk: ^3\n",
        b"name: shop\nenvironment:\n  sdk: '^3' # comment\n",
        b"name: shop\nenvironment:\n  sdk: '^4'\nenvironment:\n  sdk: '^3'\n",
    ]
    return raw


def pubspecs(root: Path) -> list[bytes]:
    return [
        path.read_bytes()
        for path in sorted(root.rglob("pubspec.yaml"))
        if path.is_file() and not path.is_symlink() and ".git" not in path.parts
    ]


def hostile_snapshots(binary: Path, scratch: Path) -> Result:
    """Check SDK gaps through safe snapshot reads, even when sources are hostile or rejected."""
    paths = [
        "plain.dart",
        "odd path.dart",
        "line\nbreak.dart",
        "é.dart",
        "x-y.dart",
        "x_y.dart",
        ".dart",
        "nested/empty.dart",
        "9bad.dart",
        "nested/deeper/a.dart",
    ]
    contents = [
        b"",
        b"\xff",
        b"\xef\xbb\xbfclass A {}",
        b" \n\t",
        b"part of 'a.dart';",
        b"part 'b.dart';",
        b"class A {} class A {}",
        b"import 'a.dart' if (dart.library.io) 'b.dart';",
        b"export 'a.dart' if (dart.library.html) 'c.dart';",
        b"class A {}",
    ]
    result = Result("hostile filesystem snapshots")
    for index, metadata in enumerate(hostile()):
        root = scratch / f"sdk-hostile-{index}"
        root.mkdir()
        (root / "pubspec.yaml").write_bytes(metadata)
        source = root / "lib" / paths[index % len(paths)]
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(contents[index % len(contents)])
        if index == 30:
            source.write_bytes(b"/" * (4 * 1024 * 1024 + 1))
        if index == 31:
            (root / "lib/x-y.dart").write_text("class A {}")
            (root / "lib/x_y.dart").write_text("class A {}")
        if os.name != "nt" and index in {20, 21, 22}:
            if index == 20:
                (root / "lib/link.dart").symlink_to(source)
            elif index == 21:
                (root / "lib/linked").symlink_to(root / "lib", target_is_directory=True)
            else:
                (root / "pubspec.yaml").unlink()
                (root / "pubspec.yaml").symlink_to(source)
        corpus = Corpus("hostile", root, ("lib",), "shop")
        actual = discovery_native(binary, corpus)
        result.files += 1
        try:
            snapshot = read_snapshot(request(corpus))
        except SnapshotError as error:
            result.equal += same_error(actual.get("error"), str(error))
            continue
        item: Input = {
            "state": snapshot.sdk_constraint_state.value,
            "constraint": snapshot.sdk_constraint,
        }
        if "error" in actual:
            continue
        actual_selected = actual["selected_files"]
        assert isinstance(actual_selected, list)
        raw_gaps = actual["gaps"]
        assert isinstance(raw_gaps, list)
        gaps = [gap for gap in raw_gaps if gap["kind"] == "SdkConstraintError"]
        boundary = native(binary, [item])[0]
        selected = [source.rel_path for source in snapshot.sources]
        if canonical(gaps) != canonical(boundary["gaps"]):
            continue
        if actual_selected != selected:
            # AD-365 bounds a native source read at 4 MiB; Python has no source size bound.
            missing = set(selected) - set(actual_selected)
            size_paths = {
                gap["data"]["file"]
                for gap in raw_gaps
                if gap["kind"] == "SnapshotError"
                and gap["data"]["message"] == "source file is over the size limit of 4194304 bytes"
            }
            if missing and missing == size_paths and set(actual_selected) < set(selected):
                result.stricter += 1
            continue
        if any(
            "SdkConstraintWorkLimit" in gap["data"]["message"]
            or "SdkConstraintDigitLimit" in gap["data"]["message"]
            for gap in gaps
        ):
            result.stricter += 1
        else:
            result.equal += canonical(payload(boundary)) == canonical(python(item))
    result.different = result.files - result.equal - result.stricter
    return result


def run(binary: Path, *, demos: bool, items: Sequence[str], scratch: Path) -> list[Result]:
    results = [compare(binary, "hostile metadata", hostile()), hostile_snapshots(binary, scratch)]
    if demos:
        for name in FIXTURES:
            results.append(compare(binary, name, pubspecs(ROOT / "fixtures" / name)))
        raw = [data for corpus in demo_variants(scratch) for data in pubspecs(corpus.root)]
        results.append(compare(binary, "demo variants", raw))
    for item in items:
        name, separator, path = item.partition("=")
        if not separator:
            raise ValueError("a corpus must be NAME=PATH")
        results.append(compare(binary, name, pubspecs(Path(path))))
    return results


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--demos", action="store_true")
    args.add_argument("--corpus", action="append", default=[])
    options = args.parse_args()
    if (sys.version_info[:2], unicodedata.unidata_version) != ((3, 11), "14.0.0"):
        raise SystemExit("the oracle is Python 3.11 with Unicode 14.0.0")
    with TemporaryDirectory() as scratch:
        results = run(build(), demos=options.demos, items=options.corpus, scratch=Path(scratch))
    print("set | inputs | equal | stricter (SDK work/digit or snapshot size limit) | different")
    for row in results:
        print(f"{row.name} | {row.files} | {row.equal} | {row.stricter} | {row.different}")
    return int(any(row.different for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
