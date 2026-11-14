# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Refuse a release whose wheels do not carry a core that decides (AD-432, AD-436).

The Python shell decides nothing. A wheel without `archkeel-core` gives a package that refuses each
run, so the release build runs this check on `dist/` before it uploads a distribution. Each wheel
must hold the core binary and the digest of that binary, and its platform must be one of
`PLATFORM_TAGS`, each exactly once: Full builds, installs and runs those wheels on their platforms
(AD-476). The wheel of the build host, installed alone, must give a verdict of its own core for a
fixture. Full verification installs the wheel of each other target on that target.

Run: `python -m tools.release_core <dist> <wheel of this host>`. Exit 0 or 2.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

MEMBER = "archkeel/_native/archkeel-core"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/H-typescript"


def platform_tags() -> tuple[str, ...]:
    """The platforms of a release. A lazy import: mypy would find the module under two names."""
    tags: tuple[str, ...] = importlib.import_module("tools.publish_release").PLATFORM_TAGS
    return tags


def carries_core(wheel: Path) -> bool:
    """Whether the wheel holds the binary and its digest, as `cli/core_binary.py` reads them."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            for name in (MEMBER, MEMBER + ".exe"):
                if {name, name + ".sha256"} <= names:
                    recorded = archive.read(name + ".sha256").decode("ascii", errors="replace")
                    return recorded == hashlib.sha256(archive.read(name)).hexdigest()
    except (OSError, zipfile.BadZipFile):
        return False
    return False


def undecided(result: object, code: int) -> str:
    """Why a result of `validate --json` is no verdict of the bundled core; empty when it is one."""
    if not isinstance(result, dict):
        return f"no result object: {result!r}"
    if "refusal" in result:
        refusal = result["refusal"]
        return f"refusal {refusal.get('kind') if isinstance(refusal, dict) else refusal}"
    frame, core = result.get("frame"), result.get("core")
    frame = frame if isinstance(frame, dict) else {}
    engine = frame.get("engine")
    if not isinstance(engine, str) or not engine.startswith("archkeel-core "):
        return "the result has no frame of archkeel-core"
    path = core.get("path") if isinstance(core, dict) else None
    if not isinstance(path, str) or Path(path).parent.name != "_native":
        return f"the core is not the binary of the package: {path!r}"
    rows = frame.get("rules")
    if not isinstance(rows, dict) or not any("PASS" in row for row in rows.values()):
        return "no rule has PASS for the fixture"
    if result.get("exit_code") != code:
        return f"exit code {code} differs from the result"
    return ""


def smoke(wheel: Path) -> str:
    """Install the wheel alone and validate the fixture; why it gives no verdict, else empty."""
    command = ["uv", "run", "--isolated", "--no-project", "--with", str(wheel), "python", "-m"]
    command += ["archkeel.cli", "validate", "--root", str(FIXTURE), "--json"]
    try:
        run = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        return f"uv did not start: {error}"
    try:
        result = json.loads(run.stdout)
    except ValueError:
        return f"no JSON result, exit {run.returncode}: {run.stderr.strip()[-300:]}"
    return undecided(result, run.returncode)


def problems(dist: Path, host: Path) -> list[str]:
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        return [f"{dist} holds no wheel"]
    found = [f"{wheel.name} does not carry {MEMBER} and its digest" for wheel in wheels]
    found = [line for line, wheel in zip(found, wheels, strict=True) if not carries_core(wheel)]
    tags = sorted(wheel.stem.split("-", 2)[2] for wheel in wheels)
    if tags != sorted(platform_tags()):
        found.append(f"the wheels {tags} are not exactly the platforms {sorted(platform_tags())}")
    if found:
        return found
    if host.resolve() not in {wheel.resolve() for wheel in wheels}:
        return [f"{host} is not a wheel of {dist}"]
    why = smoke(host)
    return [f"{host.name}, installed alone, gives no verdict of its core: {why}"] if why else []


def main(arguments: list[str]) -> int:
    if len(arguments) != 2:
        print(f"release refused: {__doc__.splitlines()[-1].strip()}", file=sys.stderr)
        return 2
    found = problems(Path(arguments[0]), Path(arguments[1]))
    for line in found:
        print(f"release refused: {line}", file=sys.stderr)
    if found:
        print("A package without a core that decides refuses each run (AD-436).", file=sys.stderr)
    return 2 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
