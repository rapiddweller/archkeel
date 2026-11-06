"""Compare the Rust syntax batch with CPython's AST on a public synthetic fixture."""

import ast
import json
import subprocess
from pathlib import Path

SOURCE = """# λ before source locations
é = 1
import café
import os, package.sub as alias
from .internal import thing as local
from .. import sibling
from pkg.sub import (
    first,
    second as second_alias,
)
def load():
    from .nested import item as nested_item
"""


class Imports(ast.NodeVisitor):
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.add("import", None, 0, node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.add("from", node.module, node.level, node.names)
        self.generic_visit(node)

    def add(self, form: str, module: str | None, level: int, aliases: list[ast.alias]) -> None:
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


def main() -> None:
    binary = Path(__file__).parent / "target/debug/archkeel-import-facts-spike"
    actual = json.loads(
        subprocess.run([binary], input=SOURCE, text=True, capture_output=True, check=True).stdout
    )
    reference = Imports()
    reference.visit(ast.parse(SOURCE))
    expected = {
        "status": "COMPLETE",
        "complete": True,
        "reason": None,
        "target_python_version": "3.11",
        "semantic_status": "UNKNOWN",
        "unknown": ["target_resolution", "reexport_semantics"],
        "imports": sorted(
            reference.items,
            key=lambda item: (
                item["line"],
                item["column"],
                item["end_line"],
                item["end_column"],
                item["name"],
            ),
        ),
    }
    assert actual == expected, json.dumps({"actual": actual, "expected": expected}, indent=2)
    print(f"Python AST parity: {len(expected['imports'])} import occurrences")


if __name__ == "__main__":
    main()
