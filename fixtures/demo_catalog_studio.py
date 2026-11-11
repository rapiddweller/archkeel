# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 runtime catalog for Studio's local CLI session lifecycle."""

from __future__ import annotations

import io
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from archkeel.cli import root_digest
from archkeel.cli.arguments import Command


@dataclass(frozen=True)
class StudioDemoVariant:
    """One runtime scenario; separate from the static architecture-report Variant."""

    id: str
    active_language: str
    requested_language: str
    source: str
    mismatch_exit: int
    stop_exit: int


CATALOG: tuple[StudioDemoVariant, ...] = (
    StudioDemoVariant(
        id="studio-scope-mismatch-stop",
        active_language="python",
        requested_language="typescript",
        source="src",
        mismatch_exit=2,
        stop_exit=0,
    ),
)

_START_SECONDS = 90


def _child_environment(cache: Path | None = None) -> dict[str, str]:
    """Keep caller Git redirection and config out of every demo child process."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if cache is not None:
        environment["XDG_CACHE_HOME"] = str(cache)
    return environment


def _fixture(root: Path) -> None:
    """Create a small committed Python project with no external or private inputs."""
    hooks = root.parent / "empty-hooks"
    hooks.mkdir()
    git_environment = _child_environment()
    (root / "src/demo").mkdir(parents=True)
    (root / "src/demo/__init__.py").write_text("", encoding="utf-8")
    (root / "src/demo/service.py").write_text(
        "def price(quantity: int, unit_price: int) -> int:\n    return quantity * unit_price\n",
        encoding="utf-8",
    )
    for arguments in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        [
            "-c",
            "user.name=ArchKeel demo",
            "-c",
            "user.email=demo@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "demo fixture",
        ],
    ):
        subprocess.run(
            ["git", "-c", f"core.hooksPath={hooks}", *arguments],
            cwd=root,
            env=git_environment,
            check=True,
            capture_output=True,
            timeout=10,
        )


def _read_start(output: io.TextIOBase, child: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + _START_SECONDS
    while time.monotonic() < deadline:
        output.flush()
        output.seek(0)
        if output.readline().startswith("ArchKeel Studio: http://127.0.0.1:"):
            return
        if child.poll() is not None:
            raise RuntimeError("Studio exited before it became ready")
        time.sleep(0.05)
    raise TimeoutError("Studio did not become ready within the demo timeout")


def _cleanup_group(process: subprocess.Popen[bytes]) -> None:
    """Stop an isolated process group even when startup or cleanup gets stuck."""
    try:
        if process.poll() is None:
            process.terminate()
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        if process.poll() is None:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def _run_cli(root: Path, cache: Path, *arguments: str) -> tuple[int, str]:
    """Run one real CLI command with a deadline and an isolated cleanup group."""
    client = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archkeel.cli",
            "studio",
            "--root",
            str(root),
            "--no-open",
            *arguments,
        ],
        cwd=root,
        env=_child_environment(cache),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = client.communicate(timeout=30)
    except subprocess.TimeoutExpired as error:
        _cleanup_group(client)
        raise TimeoutError("Studio CLI command exceeded 30 seconds") from error
    return client.returncode, output


def _run_clients(root: Path, cache: Path, variant: StudioDemoVariant) -> None:
    """Exercise scope refusal and stop in separate, bounded CLI processes."""
    mismatch_exit, mismatch = _run_cli(
        root,
        cache,
        "--language",
        variant.requested_language,
        "--source",
        variant.source,
    )
    if (
        mismatch_exit != variant.mismatch_exit
        or "different or unknown scope" not in mismatch
        or "--stop" not in mismatch
    ):
        raise RuntimeError("scope mismatch did not give the expected safe-stop guidance")

    stop_exit, stopped = _run_cli(root, cache, "--stop")
    if stop_exit != variant.stop_exit or "stopped" not in stopped:
        raise RuntimeError("the active Studio did not stop cleanly")


def run(variant: StudioDemoVariant) -> str:
    """Run the real CLI twice: reject a new scope, then stop the active session."""
    if os.name == "nt":
        raise RuntimeError(
            "this demo needs POSIX graceful stop; Windows cleanup is not yet supported"
        )
    with tempfile.TemporaryDirectory(prefix="archkeel-studio-demo-") as temporary:
        workspace = Path(temporary)
        root = workspace / "project"
        cache = workspace / "cache"
        root.mkdir()
        _fixture(root)
        environment = _child_environment(cache)
        output_path = workspace / "server.stdout"
        error_path = workspace / "server.stderr"
        with (
            output_path.open("w+", encoding="utf-8") as output,
            error_path.open("w+", encoding="utf-8") as error,
        ):
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "archkeel.cli",
                    "studio",
                    "--root",
                    str(root),
                    "--no-open",
                    "--language",
                    variant.active_language,
                    "--source",
                    variant.source,
                ],
                cwd=root,
                env=environment,
                stdout=output,
                stderr=error,
                start_new_session=True,
            )
            try:
                _read_start(output, server)
                _run_clients(root, cache, variant)
                if server.wait(timeout=20) != 0:
                    raise RuntimeError("Studio did not exit cleanly after --stop")

                session = cache / "archkeel" / Command.EXPLORE.value / root_digest(root.resolve())
                if (session / "studio.json").exists() or list(session.glob("studio-*")):
                    raise RuntimeError("Studio left state or a run folder in the demo cache")
                return (
                    "mismatch refused with exit 2; --stop exited 0; server and run folder cleaned"
                )
            finally:
                _cleanup_group(server)


def main() -> int:
    variant = CATALOG[0]
    if os.name == "nt":
        print(
            f"{variant.id}: SKIP (Windows `--stop` cannot clean the Explore child yet)",
            file=sys.stderr,
        )
        return 0
    try:
        outcome = run(variant)
    except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        print(f"{variant.id}: FAIL ({error})", file=sys.stderr)
        return 1
    print(f"{variant.id}: PASS ({outcome})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
