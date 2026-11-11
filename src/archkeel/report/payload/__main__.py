# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Write the report v2 payload next to a saved report (AD-361).

    archkeel report --output build/architecture.json --json > build/result.json
    python -m archkeel.report.payload build/architecture.json --result build/result.json

The current report does not change. The payload goes to `<stem>.report-v2.json` by default.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from archkeel.report.payload import PayloadTooLarge, build_payload, evaluation


def default_output(architecture: Path) -> Path:
    """Return the payload path next to architecture.json."""
    return architecture.with_name(architecture.stem + ".report-v2.json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m archkeel.report.payload", description=__doc__.splitlines()[0]
    )
    parser.add_argument("architecture", type=Path, help="A saved architecture.json.")
    parser.add_argument(
        "--result",
        type=Path,
        required=True,
        help="The JSON result of the same `archkeel report` run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Payload path. Default: <stem>.report-v2.json next to the input.",
    )
    args = parser.parse_args(argv)
    document = json.loads(args.architecture.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    try:
        data = build_payload(document, evaluation(result))
    except PayloadTooLarge as error:
        print(f"archkeel: {error}", file=sys.stderr)
        return 2
    output = args.output or default_output(args.architecture)
    output.write_bytes(data)
    print(f"{output} {len(data)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
