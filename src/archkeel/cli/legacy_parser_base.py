# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""Shared parser types, converters and defaults, without an engine import at module load."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final, NoReturn

if TYPE_CHECKING:
    from .arguments import CLIArguments

_DOCS: Final = "https://github.com/rapiddweller/archkeel/blob/main/docs"

_ARCHITECTURE_JSON: Final = "architecture.json"

_SNAPSHOT_PATH: Final = Path("test-artifacts/architecture") / _ARCHITECTURE_JSON

_PER_RUN_LIMIT_REMEDY: Final = (
    "Retry with a larger finite --collector-output-limit-bytes value; "
    "larger values need more memory."
)


def _sha(value: str) -> str:
    if re.fullmatch("[0-9a-f]{40}", value) is None:
        raise argparse.ArgumentTypeError("must be a full lowercase Git SHA")
    return value


def _positive_bytes(value: str) -> int:
    """Parse a finite positive byte limit for one observation."""
    from ..ir.facts_codec import MAX_RESPONSE_LIMIT_BYTES

    try:
        limit = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if not 0 < limit <= MAX_RESPONSE_LIMIT_BYTES:
        raise argparse.ArgumentTypeError(
            f"must be a positive integer no greater than {MAX_RESPONSE_LIMIT_BYTES} bytes"
        )
    return limit


class _Parser(argparse.ArgumentParser):
    def parse_cli_args(self, args: Sequence[str] | None = None) -> CLIArguments:
        from .arguments import CLIArguments, Command

        arguments = argparse.ArgumentParser.parse_args(self, args, CLIArguments())
        if arguments.command is not None:
            arguments.command = Command(arguments.command)
        return arguments

    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def _observing(parser: _Parser, output_help: str | None) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Default: the current directory.",
    )
    if output_help is not None:
        parser.add_argument("--output", type=Path, help=output_help)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the JSON result even in an interactive terminal.",
    )


def _collector_output_limit(parser: _Parser) -> None:
    parser.add_argument(
        "--collector-output-limit-bytes",
        type=_positive_bytes,
        metavar="BYTES",
        help="Finite collector stdout limit for this run. Default: 67108864 (64 MiB). "
        "Higher values can use much more memory; no unlimited mode exists.",
    )
