# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replay the demo check commands in a pseudo-terminal and export each view as SVG."""

import argparse
import json
import os
import pty
import shlex
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

from fixtures.architecture_demo import CATALOG, materialized_fixture

WIDTH = 80
INSIDE_VARIANT = "class-a-complete-requires-inside"


def save_svg(console: Console, path: Path, *, title: str) -> None:
    # Fallback fonts need glyph scaling to preserve Rich's measured terminal columns.
    svg = console.export_svg(title=title).replace(
        ' textLength="', ' lengthAdjust="spacingAndGlyphs" textLength="'
    )
    path.write_text(svg, encoding="utf-8")


def capture(
    command: list[str], *, expected_exit_code: int, required_output: tuple[str, ...] = ()
) -> str:
    """Run a terminal command and reject captures that do not prove their expected result."""
    leader, follower = pty.openpty()
    env = {key: value for key, value in os.environ.items() if not key.startswith("CI_")}
    env.pop("NO_COLOR", None)
    env.update(COLUMNS=str(WIDTH), LINES="200", TERM="xterm-256color")
    process = subprocess.Popen(command, stdout=follower, stderr=follower, env=env)
    os.close(follower)
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(leader, 65536)
        except OSError:
            # Linux reports EIO once the child closes its side of the terminal.
            break
        if not chunk:
            break
        chunks.append(chunk)
    return_code = process.wait()
    os.close(leader)
    output = b"".join(chunks).decode().replace("\r\n", "\n")
    if return_code != expected_exit_code:
        raise subprocess.CalledProcessError(return_code, command, output=output)
    missing = [value for value in required_output if value not in output]
    if missing:
        raise RuntimeError(f"capture missing expected output {missing!r}: {output}")
    return output


def export(output: Path) -> list[Path]:
    exported = []
    for entry in json.loads((output / "commands.json").read_bytes()):
        command = shlex.split(entry["command"])
        if command[1] != "check":
            continue
        case = Path(command[command.index("--root") + 1]).name
        with open(os.devnull, "w") as sink:
            console = Console(record=True, width=WIDTH, file=sink, force_terminal=True)
            console.print(
                Text.from_ansi(capture(command, expected_exit_code=entry["exit_code"])),
                end="",
            )
        target = output / f"{case}-check-terminal.svg"
        save_svg(console, target, title=f"archkeel check · fixture {case}")
        exported.append(target)
    inside_target = output / "archkeel-shop-inside-violation.svg"
    with open(os.devnull, "w") as sink:
        console = Console(record=True, width=WIDTH, file=sink, force_terminal=True)
        console.print(Text.from_ansi(capture_inside_violation()), end="")
        save_svg(console, inside_target, title="archkeel validate · inside rule violation")
    exported.append(inside_target)
    return exported


def capture_inside_violation() -> str:
    """Capture the real CLI result for the catalog's three inside-rule violations."""
    variant = next((item for item in CATALOG if item.id == INSIDE_VARIANT), None)
    if variant is None:
        raise RuntimeError(f"missing architecture demo variant: {INSIDE_VARIANT}")
    with materialized_fixture(variant) as root:
        command = [
            str(Path(sys.executable).with_name("archkeel")),
            "validate",
            "--root",
            str(root),
            "--config",
            variant.config,
        ]
        output = capture(
            command,
            expected_exit_code=2,
            required_output=("NOT CHECKED", "store:STORE-REQUIRES-COMPLETE", "rule.violated"),
        )
        if output.count("rule.violated") != 3 or "PASS" in output:
            raise RuntimeError("inside-rule CLI output does not match its three-finding fixture")
        result = subprocess.run([*command, "--json"], capture_output=True, check=False, text=True)
        if result.returncode != 2:
            raise subprocess.CalledProcessError(result.returncode, command, result.stdout)
        report = json.loads(result.stdout)
        diagnostics = [(item["code"], item["subject"]) for item in report["diagnostics"]]
        expected = [("rule.violated", "store:STORE-REQUIRES-COMPLETE")] * 3
        if report["declared_rules"] != "UNKNOWN" or diagnostics != expected:
            raise RuntimeError(f"inside-rule JSON evidence changed: {report}")
        return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Directory written by make demo OUTPUT=...")
    for path in export(parser.parse_args().output):
        print(path)
