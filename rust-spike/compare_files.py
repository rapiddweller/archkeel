"""Compare explicit Python files with the Rust import parser; print counts only."""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import subprocess
import sys
import tokenize
from collections import Counter
from pathlib import Path

MAX_FILES = 100
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
MAX_CAPTURED_OUTPUT = 4 * 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 3


class Imports(ast.NodeVisitor):
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.add("import", None, 0, node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.add("from", node.module, node.level, node.names)
        self.generic_visit(node)

    def add(
        self,
        form: str,
        module: str | None,
        level: int,
        aliases: list[ast.alias],
    ) -> None:
        for alias in aliases:
            self.items.append(
                {
                    "form": form,
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname,
                    "level": level,
                    "line": alias.lineno,
                    "column": alias.col_offset,
                    "end_line": alias.end_lineno,
                    "end_column": alias.end_col_offset,
                    "semantic_status": "UNKNOWN",
                }
            )


def _sort_key(item: dict[str, object]) -> tuple[object, ...]:
    return (
        item["line"],
        item["column"],
        item["end_line"],
        item["end_column"],
        item["name"],
    )


def _is_test_file(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    return bool(parts & {"test", "tests"}) or name.startswith("test_") or name.endswith("_test.py")


def _parse_reference(source: str, minor: int) -> list[dict[str, object]] | None:
    try:
        tree = ast.parse(source, filename="<input>", feature_version=(3, minor))
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    imports = Imports()
    imports.visit(tree)
    return sorted(imports.items, key=_sort_key)


def _decode_source(raw: bytes) -> str:
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    return raw.decode(encoding)


def _compare_one(
    path: Path, binary: Path, target: str, minor: int, byte_budget: int
) -> tuple[str, int]:
    read_limit = min(MAX_FILE_BYTES, byte_budget)
    try:
        with path.open("rb") as stream:
            raw = stream.read(read_limit + 1)
    except OSError:
        return "read_error", 0
    if len(raw) > read_limit:
        category = "file_size_limit" if read_limit == MAX_FILE_BYTES else "total_size_limit"
        return category, len(raw)
    try:
        source = _decode_source(raw)
        reference = _parse_reference(source, minor)
    except (SyntaxError, UnicodeError, LookupError):
        return "source_decode_error", len(raw)

    try:
        process = subprocess.run(
            [str(binary), "--target", target],
            input=source.encode("utf-8"),
            capture_output=True,
            timeout=PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "rust_timeout", len(raw)
    except OSError:
        return "rust_process_error", len(raw)
    if len(process.stdout) > MAX_CAPTURED_OUTPUT or len(process.stderr) > MAX_CAPTURED_OUTPUT:
        return "captured_output_over_limit", len(raw)
    if process.returncode:
        return "rust_process_error", len(raw)
    try:
        batch = json.loads(process.stdout)
    except (UnicodeError, json.JSONDecodeError):
        return "rust_invalid_output", len(raw)
    if not isinstance(batch, dict):
        return "rust_invalid_output", len(raw)

    if reference is None:
        if batch.get("status") == "UNKNOWN" and not batch.get("complete"):
            return "both_rejected", len(raw)
        return "python_rejected_rust_complete", len(raw)
    if batch.get("status") != "COMPLETE" or not batch.get("complete"):
        reason = batch.get("reason")
        if reason in {"syntax_error", "unsupported_syntax", "unsupported_target_version"}:
            return f"rust_unknown_{reason}", len(raw)
        return "rust_unknown_other", len(raw)
    actual = batch.get("imports")
    if isinstance(actual, list) and actual == reference:
        return "parity", len(raw)
    return "fact_mismatch", len(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rust-binary", type=Path, required=True)
    parser.add_argument("--target", default="3.11", help="Python target, for example 3.11")
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()

    match = re.fullmatch(r"3\.(\d+)", args.target)
    if match is None:
        parser.error("--target must have the form 3.MINOR")
    minor = int(match.group(1))
    if minor < 7 or minor > sys.version_info.minor:
        parser.error("target must be supported by this CPython interpreter")
    if len(args.sources) > MAX_FILES:
        parser.error(f"pass no more than {MAX_FILES} source files")

    counts: Counter[str] = Counter()
    total_bytes = 0
    checked = 0
    for path in args.sources:
        if _is_test_file(path):
            counts["excluded_test_file"] += 1
            continue
        if total_bytes >= MAX_TOTAL_BYTES:
            counts["total_size_limit"] += 1
            continue
        category, size = _compare_one(
            path, args.rust_binary, args.target, minor, MAX_TOTAL_BYTES - total_bytes
        )
        total_bytes += size
        checked += 1
        counts[category] += 1

    print(
        json.dumps(
            {
                "target": args.target,
                "checked_files": checked,
                "input_bytes": total_bytes,
                "categories": dict(sorted(counts.items())),
                "output_limit_note": (
                    "captured output is classified after capture; this is not an RSS limit"
                ),
            },
            sort_keys=True,
        )
    )
    return int(counts.get("fact_mismatch", 0) > 0)


if __name__ == "__main__":
    raise SystemExit(main())
