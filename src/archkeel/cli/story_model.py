# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run the signed-in Codex model without project tools or configuration."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_LIMIT = 128 * 1024
_DISABLED = (
    "shell_tool",
    "unified_exec",
    "plugins",
    "computer_use",
    "code_mode_host",
    "apps",
    "browser_use",
)


def ask_story_model(prompt: str, root: Path) -> dict[str, object]:
    """Run the fixed Codex command with a private temporary configuration."""
    executable = shutil.which("codex")
    if executable is None:
        raise RuntimeError("Codex is not installed or is not on PATH")
    executable = str(Path(executable).resolve())
    if Path(executable).is_relative_to(root.resolve()):
        raise RuntimeError("Codex must be installed outside the analyzed repository")
    env = {
        k: v
        for k, v in os.environ.items()
        if re.fullmatch(
            r"PATH|HOME|USER|LOGNAME|LANG|LC_.*|TERM|TMPDIR|XDG_.*|CODEX_HOME|SSL_CERT_FILE|SSL_CERT_DIR|(?i:https?_proxy|all_proxy|no_proxy)",
            k,
        )
    }
    if Path(tempfile.gettempdir()).resolve().is_relative_to(root.resolve()):
        raise RuntimeError("Choose a temporary directory outside the analyzed repository")
    with tempfile.TemporaryDirectory(prefix="archkeel-story-agent-") as work:
        output = Path(work) / "answer.json"
        home = Path(work) / "codex-home"
        home.mkdir(mode=0o700)
        auth = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
        if not auth.is_file():
            raise RuntimeError("Codex sign-in was not found; sign in with codex login")
        try:
            (home / "auth.json").symlink_to(auth.resolve(strict=True))
        except OSError as error:
            raise RuntimeError(
                "Cannot isolate Codex sign-in; symbolic links are required"
            ) from error
        env["CODEX_HOME"] = str(home)
        command = [
            executable,
            "exec",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--ignore-user-config",
            "--skip-git-repo-check",
            *(arg for feature in _DISABLED for arg in ("--disable", feature)),
            "--color",
            "never",
            "--output-last-message",
            str(output),
            "-",
        ]
        try:
            done = subprocess.run(
                command,
                input=prompt.encode(),
                cwd=work,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("Codex could not answer; check installation and sign-in") from error
        if done.returncode != 0 or not output.is_file():
            raise RuntimeError("Codex could not answer; check installation and sign-in")
        return _answer(output)


def _answer(output: Path) -> dict[str, object]:
    if output.stat().st_size > _LIMIT:
        raise RuntimeError("The Codex answer exceeds 128 KiB")
    try:
        answer = json.loads(output.read_bytes())
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeError("Codex returned an invalid story candidate") from error
    if not isinstance(answer, dict):
        raise RuntimeError("Codex returned an invalid story candidate")
    return answer
