# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify an installed distribution: its files, its commands and its refusals (AD-432, AD-436).

Each package carries the core binary and its digest. So each deciding command must give the frame
of that binary, and a command that is not on this line must refuse. Run: `make smoke`.
"""

import json
import subprocess
import sys
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory


def files_of_the_package() -> None:
    assets = files("archkeel").joinpath("render", "assets")
    flow_digest = sha256(assets.joinpath("flow.js").read_bytes()).hexdigest()
    assert f"// Generated from flow.js; source-sha256={flow_digest}" in assets.joinpath(
        "flow.runtime.js"
    ).read_text(encoding="utf-8")
    for name in ("report-graph-protocol.js", "report-graph-scene.js", "report-atlas-deviations.js"):
        assert "Archkeel" in assets.joinpath(name).read_text(encoding="utf-8")
    # AD-290: the wheel ships what the Studio server serves, not the sources of the bundle.
    studio = files("archkeel").joinpath("studio", "ui")
    shipped = {item.name for item in studio.iterdir()}
    served = {"index.html", "studio.js", "tokens.css", "studio.css", "PREACT-LICENSE.md"}
    assert shipped == served, shipped
    schemas = files("archkeel").joinpath("schema")
    result_schema = json.loads(
        schemas.joinpath("command-result.schema.json").read_text(encoding="utf-8")
    )
    assert result_schema["$id"] == "urn:archkeel:command-result:6.0.0"
    for version in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
        name = f"studio-api-{version[:-2]}.schema.json"
        studio_api = json.loads(schemas.joinpath(name).read_text("utf-8"))
        assert studio_api["$id"] == f"urn:archkeel:studio-api:{version}"
    assert "expectation_fulfilled" in result_schema["required"]
    source_facts_5 = json.loads(
        schemas.joinpath("source-facts-5.0.schema.json").read_text(encoding="utf-8")
    )
    assert source_facts_5["$id"] == "https://archkeel.dev/schema/source-facts/5.0.0"
    python_2_7 = json.loads(
        schemas.joinpath("architecture-ir-python-decoded-2.7.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert python_2_7["$id"] == "urn:archkeel:architecture-ir:python-decoded:2.7.0"
    assert python_2_7["properties"]["calls"]["items"]["allOf"][1]["properties"]["data"][
        "properties"
    ]["call_binding"]["oneOf"][1]["$ref"] == (
        "https://archkeel.dev/schema/source-facts/5.0.0#/$defs/CallBinding"
    )
    assert source_facts_5["$defs"]["CallBinding"]["required"] == [
        "origin",
        "target",
        "evidence_ids",
    ]
    for name in (
        "architecture-ir-common.schema.json",
        "architecture-ir-python-decoded.schema.json",
        "architecture-contract.schema.json",
        "architecture-projection.schema.json",
        "architecture-command.schema.json",
        "architecture-command-2.0.schema.json",
        "command-result-7.0.schema.json",
        "command-result-8.0.schema.json",
        "command-result-9.0.schema.json",
        "command-result-10.0.schema.json",
        "command-result-11.0.schema.json",
        "command-result-12.0.schema.json",
        "command-result-13.0.schema.json",
        "architecture-ir-decoded-2.1.schema.json",
        "architecture-ir-python-decoded-2.1.schema.json",
        "architecture-ir-decoded-2.2.schema.json",
        "architecture-ir-python-decoded-2.2.schema.json",
        "architecture-ir-decoded-2.3.schema.json",
        "architecture-ir-python-decoded-2.3.schema.json",
        "architecture-ir-decoded-2.4.schema.json",
        "architecture-ir-python-decoded-2.4.schema.json",
        "architecture-ir-decoded-2.5.schema.json",
        "architecture-ir-python-decoded-2.5.schema.json",
        "architecture-contract-3.8.schema.json",
        "architecture-ir-decoded-2.8.schema.json",
        "architecture-ir-python-decoded-2.8.schema.json",
        "architecture-contract-3.14.schema.json",
        "architecture-ir-decoded-2.9.schema.json",
        "architecture-ir-python-decoded-2.9.schema.json",
        "architecture-ir-decoded-2.10.schema.json",
        "architecture-ir-python-decoded-2.10.schema.json",
        "source-facts-4.0.schema.json",
        "source-facts-5.0.schema.json",
        "source-facts.schema.json",
    ):
        assert json.loads(schemas.joinpath(name).read_text(encoding="utf-8"))["$id"]


REFUSED = ("check", "explore", "init", "guide", "story", "view", "studio")


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "archkeel.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def refusal(run: subprocess.CompletedProcess[str], kind: str) -> str:
    """The message of a typed refusal: exit 2, status UNKNOWN, no verdict and no traceback."""
    assert run.returncode == 2, (run.stdout, run.stderr)
    assert "Traceback" not in run.stderr, run.stderr
    result = json.loads(run.stdout)
    assert result["status"] == "UNKNOWN" and result["exit_code"] == 2, result
    assert set(result) == {"status", "exit_code", "refusal"}, result
    assert result["refusal"]["kind"] == kind, result
    return str(result["refusal"]["message"])


def decided(run: subprocess.CompletedProcess[str], native: Path) -> None:
    """The run gives the frame of the core of the package: PASS for the project, exit 0."""
    assert run.returncode == 0 and "Traceback" not in run.stderr, (run.stdout, run.stderr)
    result = json.loads(run.stdout)
    assert result["status"] == "PASS" and result["exit_code"] == 0, result
    assert "refusal" not in result, result
    assert Path(result["core"]["path"]).parent == native, result["core"]
    assert result["frame"]["engine"].startswith("archkeel-core "), result["frame"]["engine"]
    assert result["frame"]["rules"] == {"NO-CYCLES": ["no_component_cycles", "PASS"]}, result


CONTRACT = {
    "schema_version": "2.1.0",
    "components": [
        {
            "id": "COMP-APP",
            "label": "app",
            "role": "component",
            "packages": ["app.src"],
            "responsibilities": ["Own the source."],
            "forbidden_responsibilities": [],
            "provenance": ["tsconfig.json", "architecture.md"],
            "requires": [],
            "decided_by": "architect",
        }
    ],
    "rules": [
        {
            "id": "NO-CYCLES",
            "kind": "no_component_cycles",
            "rationale": "The components have no cycle.",
            "provenance": ["tsconfig.json"],
            "decided_by": "architect",
        }
    ],
}


GRAPH = (
    "# Architecture\n\n<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n    app\n```\n"
)


def commit(root: Path) -> None:
    # The core reads a Git work tree with a commit.
    git = ["git", "-c", "user.email=qa@example.invalid", "-c", "user.name=QA"]
    for step in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run([*git, "-c", "commit.gpgsign=false", *step], cwd=root, check=True)


def commands() -> None:
    native = Path(str(files("archkeel").joinpath("_native")))
    held = sorted(item.name.replace(".exe", "") for item in native.iterdir())
    assert held == ["archkeel-core", "archkeel-core.sha256"], held
    with TemporaryDirectory(prefix="archkeel-smoke-") as temporary:
        root = Path(temporary).resolve()
        (root / "src").mkdir()
        (root / "src/a.ts").write_text("export const a = 1;\n")
        (root / "tsconfig.json").write_text('{"include": ["src"]}\n')
        (root / "architecture-contract.json").write_text(json.dumps(CONTRACT) + "\n")
        # AD-466: contract hygiene asks for one marked component graph in a provenance document.
        (root / "architecture.md").write_text(GRAPH)
        (root / "archkeel.toml").write_text(
            '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
        )
        commit(root)
        version = cli("--version")
        assert version.returncode == 0 and version.stdout.startswith("archkeel "), version
        assert cli("--help").returncode == 0
        for command in ("validate", "report"):
            for extra in ((), ("--core-only",)):
                decided(cli(command, "--root", str(root), "--json", *extra), native)
            text = cli(command, "--root", str(root), "--text")
            assert text.returncode == 0, (text.stdout, text.stderr)
            assert text.stdout.startswith(f"{command}: PASS\n"), text.stdout
        for command in REFUSED:
            message = refusal(
                cli(command, "--root", str(root), "--json"), "not_on_this_development_line"
            )
            remedy = "use release 4.0.1" if command in {"check", "init"} else "no release has it"
            assert remedy in message and "#880" in message, message
        removed = cli("validate", "--root", str(root), "--native-core", "--json")
        message = refusal(removed, "not_on_this_development_line")
        assert "--native-core" in message and "no release has it" in message, message
        skill = cli("skill", "install", "codex", "--root", str(root), "--json")
        assert skill.returncode == 0, (skill.stdout, skill.stderr)
        installed = (root / ".agents/skills/archkeel/SKILL.md").read_text(encoding="utf-8")
        assert "archkeel validate" in installed


if __name__ == "__main__":
    files_of_the_package()
    commands()
