# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# Auxiliary actual-report size diagnosis; does not alter the guard or product.
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path("tests").resolve()))
from test_atlas_report import _page, _sample

with tempfile.TemporaryDirectory() as directory:
    page = _page(_sample(Path(directory)))
    segments = []
    for kind in ("script", "style"):
        for match in re.finditer(r"<" + kind + r"\b([^>]*)>(.*?)</" + kind + r">", page, re.S):
            segments.append({"kind": kind, "attributes": match[1], "bytes": len(match[2].encode())})
    assets = {path.name: path.stat().st_size for path in Path("src/archkeel/render/assets").iterdir() if path.is_file()}
    total = len(page.encode())
    largest = sorted(segments, key=lambda entry: entry["bytes"], reverse=True)
    print("ACTUAL_REPORT_SIZE=" + json.dumps({"total": total, "budget": 2000000, "over": total - 2000000, "other_than_scripts_and_styles": total - sum(entry["bytes"] for entry in segments), "segments": largest, "assets": assets}, sort_keys=True))
