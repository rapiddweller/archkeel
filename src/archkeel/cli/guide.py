# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Write or verify the contract guide; the guide itself is rendered in `render.guide`."""

import sys
from pathlib import Path
from typing import Final

from archkeel.render.guide import render_guide

from .config import parse_config, project_name

GUIDE_PATH: Final = "docs/architecture/contract-guide.md"


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def run_guide(root: Path, config_path: str, output: Path | None, check: bool) -> int:
    """Read the contract, render the guide, then write it or compare it with the file on disk."""
    config_file: Path = root / config_path
    try:
        payload = config_file.read_bytes()
    except FileNotFoundError:
        return _fail(f"No contract found at {config_file}. Run archkeel init first.")
    except OSError as error:
        return _fail(f"Cannot read {config_file}: {error}")
    try:
        config = parse_config(payload, config_path)
    except ValueError as error:
        return _fail(f"Cannot read {config_path}: {error}")
    contract_file: Path = root / config.contract
    if not contract_file.is_file():
        return _fail(f"No contract found at {contract_file}. Run archkeel init first.")
    try:
        text: str = render_guide(
            contract_file.read_bytes(),
            repository=project_name(root, config),
            contract_path=config.contract,
        )
    except (OSError, ValueError) as error:
        return _fail(f"Cannot read contract at {contract_file}: {error}")
    expected: bytes = text.encode("utf-8")
    target: Path = root / (output or GUIDE_PATH)
    # resolve() follows symlinks, so an alias of the contract is refused too.
    if target.resolve() in (contract_file.resolve(), config_file.resolve()):
        return _fail(f"Refusing to overwrite {target}: it is the contract or the configuration.")
    if check:
        if not target.is_file():
            print(f"Missing: {target}. Run archkeel guide.")
            return 1
        if target.read_bytes() != expected:
            print(f"Out of date: {target}. Run archkeel guide.")
            return 1
        return 0
    directory: Path = target.parent
    directory.mkdir(parents=True, exist_ok=True)
    target.write_bytes(expected)
    print(f"Wrote {target}")
    return 0
