# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
HEADER = "\n".join(
    (
        "# Codekeel",
        "# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.",
        "# SPDX-License-Identifier: MIT",
        "",
    )
).encode()
FORBIDDEN = (
    b"/" + b"Users/",
    b"/" + b"home/",
    b"/" + b"private/tmp",
    b"/" + b"tmp/",
    b"/" + b"var/folders",
    b"C:" + bytes([92]),
)
TRACKED = tuple(
    ROOT / name
    for name in subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True).split("\0")
    if name
)


def test_tracked_python_files_have_license_header() -> None:
    assert TRACKED
    missing = [
        str(path.relative_to(ROOT))
        for path in TRACKED
        if path.suffix == ".py" and not path.read_bytes().startswith(HEADER)
    ]
    assert missing == []


def test_tracked_text_has_no_local_absolute_paths() -> None:
    hits = []
    for path in TRACKED:
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        for line, text in enumerate(payload.splitlines(), 1):
            if any(prefix in text for prefix in FORBIDDEN):
                hits.append(f"{path.relative_to(ROOT)}:{line}")
    assert hits == []
