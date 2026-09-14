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
from pathlib import Path

from rich.console import Console
from rich.text import Text

WIDTH = 80


def capture(command: list[str]) -> str:
    """Run a command whose stdout is a terminal, so Archkeel prints its Rich view."""
    leader, follower = pty.openpty()
    env = {key: value for key, value in os.environ.items() if not key.startswith("CI_")}
    env.pop("NO_COLOR", None)
    env.update(COLUMNS=str(WIDTH), LINES="200", TERM="xterm-256color")
    process = subprocess.Popen(command, stdout=follower, stderr=subprocess.DEVNULL, env=env)
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
    process.wait()
    os.close(leader)
    return b"".join(chunks).decode().replace("\r\n", "\n")


def export(output: Path) -> list[Path]:
    exported = []
    for entry in json.loads((output / "commands.json").read_bytes()):
        command = shlex.split(entry["command"])
        if command[1] != "check":
            continue
        case = Path(command[command.index("--root") + 1]).name
        with open(os.devnull, "w") as sink:
            console = Console(record=True, width=WIDTH, file=sink, force_terminal=True)
            console.print(Text.from_ansi(capture(command)), end="")
        target = output / f"{case}-check-terminal.svg"
        console.save_svg(str(target), title=f"archkeel check · fixture {case}")
        exported.append(target)
    return exported


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Directory written by make demo OUTPUT=...")
    for path in export(parser.parse_args().output):
        print(path)
