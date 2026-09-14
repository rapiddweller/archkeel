# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# Run from the Archkeel checkout with the report's exact Python version:
# PYTHONPATH=src "$PYTHON" tools/classify_unresolved.py --root "$SOURCE_ROOT" \
#   --report "$REPORT" --output "$OUTPUT"
# SOURCE_ROOT must contain archkeel.toml and the source matching the report digest.
# stdout: JSON summary; OUTPUT: summary plus one row per unresolved call.
# Expected for the reports in docs/known-limits.md (exit 0):
# D-self, Python 3.11.12: files=28, calls_total=1322, unresolved=237, unmatched=0.
# Top five: Attribute(Name)=160, Attribute(Call)=31, Name=18,
# Attribute(Attribute)=9, Attribute(Subscript)=8; top5_total=226.
# Repo #2, Python 3.12.10: files=67, calls_total=4318, unresolved=998, unmatched=0.
# Top five: Attribute(Call)=385, Attribute(Name)=382, Attribute(Await)=116,
# Attribute(Attribute)=68, Name=23; top5_total=974.

"""Count unresolved call syntax; stop if report and source no longer agree."""

import argparse
import ast
import hashlib
import json
import platform
import tomllib
from collections import Counter
from decimal import Decimal
from pathlib import Path

from archkeel.ir.codec import decode_canonical_model

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
report = decode_canonical_model(json.loads(args.report.read_bytes()))
assert platform.python_version() == report["python_version"]
scan = tomllib.loads((args.root / "archkeel.toml").read_text())["scan"]
paths = sorted(
    (
        p
        for root in scan["roots"]
        for p in (args.root / root).rglob("*.py")
        if "__pycache__" not in p.parts
    ),
    key=lambda p: p.relative_to(args.root).as_posix(),
)
digest = hashlib.sha256()
nodes = {}
for path in paths:
    relative = path.relative_to(args.root).as_posix()
    raw = path.read_bytes()
    digest.update(relative.encode() + b"\0" + raw + b"\0")
    for node in ast.walk(ast.parse(raw, filename=relative)):
        if isinstance(node, ast.Call):
            key = (relative, node.lineno, node.end_lineno, node.col_offset, ast.unparse(node.func))
            assert key not in nodes, key
            nodes[key] = node
assert digest.hexdigest() == report["source"]["source_digest"]
assert len(paths) == report["coverage"]["files_parsed"]
evidence = {e["id"]: e for e in report["evidence"]}
rows = []
for record in report["calls"]:
    if record["data"]["status"] != "unresolved":
        continue
    assert len(record["evidence_ids"]) == 1
    e = evidence[record["evidence_ids"][0]]
    key = (e["file"], e["line"], e["end_line"], e["column"], record["data"]["expression"])
    func = nodes[key].func
    shape = type(func).__name__
    if isinstance(func, ast.Attribute):
        shape += "(" + type(func.value).__name__ + ")"
    rows.append(
        dict(
            id=record["id"],
            file=e["file"],
            line=e["line"],
            end_line=e["end_line"],
            column=e["column"],
            expression=key[-1],
            shape=shape,
            reason=record["data"]["reason"],
        )
    )
assert len({r["id"] for r in rows}) == len(rows) == report["coverage"]["calls_unresolved"]
counts = Counter(r["shape"] for r in rows)


def percentage(n: int, total: int) -> str:
    return str(Decimal(n) * 100 / Decimal(total))


summary = dict(
    python_version=platform.python_version(),
    source_digest=digest.hexdigest(),
    report_sha256=hashlib.sha256(args.report.read_bytes()).hexdigest(),
    files_parsed=len(paths),
    calls_total=report["coverage"]["calls_analyzed"],
    unresolved=len(rows),
    unmatched=0,
    unresolved_percent=percentage(len(rows), report["coverage"]["calls_analyzed"]),
    counts=dict(counts.most_common()),
    percentages={k: percentage(v, len(rows)) for k, v in counts.most_common()},
    reasons=dict(Counter(r["reason"] for r in rows)),
    top5_total=sum(v for _, v in counts.most_common(5)),
    top5_percent=percentage(sum(v for _, v in counts.most_common(5)), len(rows)),
)
args.output.write_text(json.dumps(dict(summary=summary, calls=rows), indent=2) + "\n")
print(json.dumps(summary, indent=2))
