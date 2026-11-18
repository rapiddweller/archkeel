# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publish the tested Linux wheel as the container image of the current main build."""

import os
import subprocess
from pathlib import Path

TAG = "5.0-rc"
SMOKE_TEST = Path("tests/smoke_test.py").resolve()
REVISION = "org.opencontainers.image.revision"


def command(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def exists(image: str) -> bool:
    inspect = subprocess.run(["docker", "manifest", "inspect", image], capture_output=True)
    return inspect.returncode == 0


def main() -> None:
    wheels = sorted(Path("image-context").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"Expected one wheel in image-context: {wheels}")
    wheel = wheels[0].name
    sha = os.environ["GITHUB_SHA"]
    repo = os.environ["GITHUB_REPOSITORY"]
    version = wheel.split("-")[1]
    # hatch-vcs puts the abbreviated commit after "+g". An older wheel must not carry this commit.
    _, marker, abbreviated = version.partition("+g")
    if not marker or not sha.startswith(abbreviated):
        raise ValueError(f"The wheel {wheel} was not built from {sha}")
    image = f"ghcr.io/{repo.lower()}"
    pinned = f"{image}:sha-{sha}"
    if exists(pinned):
        command("docker", "pull", pinned)
    else:
        command(
            "docker",
            "build",
            "--file",
            "docker/Dockerfile",
            "--build-arg",
            f"WHEEL={wheel}",
            "--label",
            f"{REVISION}={sha}",
            "--label",
            f"org.opencontainers.image.version={version}",
            "--tag",
            pinned,
            "image-context",
        )
        command(
            "docker",
            "run",
            "--rm",
            "--volume",
            f"{SMOKE_TEST}:/smoke_test.py:ro",
            "--entrypoint",
            "python",
            pinned,
            "/smoke_test.py",
        )
        command("docker", "push", pinned)
    label = f'{{{{index .Config.Labels "{REVISION}"}}}}'
    if command("docker", "image", "inspect", pinned, "--format", label).strip() != sha:
        raise ValueError(f"The image {pinned} does not carry the revision {sha}")
    head = command("gh", "api", f"repos/{repo}/git/ref/heads/main", "--jq", ".object.sha").strip()
    if head != sha:
        print(f"main moved to {head}; {image}:{TAG} stays as it is")
        return
    command("docker", "tag", pinned, f"{image}:{TAG}")
    command("docker", "push", f"{image}:{TAG}")


if __name__ == "__main__":
    main()
