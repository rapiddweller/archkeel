# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Local protocol fixtures. Host events and CI lock authorship are simulated."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import mkdtemp

from archkeel.check.delta import build_architecture_delta
from archkeel.check.expectation import EXPECTATION_SCHEMA_VERSION, GUARDRAIL_KEYS, sha256_bytes
from archkeel.check.ratchets import measure_python_ratchets
from archkeel.cli.config import load_config
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_canonical_model,
    delta_payload,
    parse_observation,
)
from archkeel.ir.digest import package_digest
from archkeel.producer import observe


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=root, stderr=subprocess.PIPE, text=True
    ).strip()


def _json(path: Path, value: object) -> bytes:
    payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(payload)
    return payload


def minimal_contract(path: str) -> dict:
    return {
        "schema_version": "1.1.0",
        "capabilities": [
            {
                "id": "CAP-APP",
                "name": "application",
                "label": "Application",
                "review_order": 1,
                "provenance": [path],
            }
        ],
        "components": [],
        "review_scopes": [],
        "public_api": [],
        "public_api_provenance": [path],
        "public_commands": [],
        "context_roots": [],
        "context_roots_provenance": [path],
        "paths": [],
        "spot_owners": [],
        "rules": [],
    }


def reproduce(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    commands = []
    cli = str(Path(sys.executable).with_name("archkeel"))

    def command(args: list[str], *, expected: int, label: str) -> dict:
        env = {key: value for key, value in os.environ.items() if not key.startswith("CI_")}
        result = subprocess.run([cli, *args], capture_output=True, text=True, env=env)
        (output / (label + ".stdout.json")).write_text(result.stdout)
        (output / (label + ".stderr")).write_text(result.stderr)
        commands.append({"command": shlex.join([cli, *args]), "exit_code": result.returncode})
        _json(output / "commands.json", commands)
        assert result.returncode == expected, (
            label,
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return json.loads(result.stdout)

    results = {}
    for case, name, code in [("A", "A-dispatch", 1), ("B", "B-posthoc", 1), ("C", "C-valid", 0)]:
        root = output / case
        root.mkdir()
        remote = output / (case + "-origin.git")
        _git(output, "init", "--bare", "-q", str(remote))
        _git(root, "init", "-q", "-b", "main")
        _git(root, "config", "user.email", "fixture@example.invalid")
        _git(root, "config", "user.name", "Fixture CI")
        _git(root, "remote", "add", "origin", str(remote))
        (root / "sample").mkdir()
        (root / "sample/__init__.py").write_text("")
        (root / "sample/helpers.py").write_text(
            "def first() -> int:\n    return 1\n\n\ndef second() -> int:\n    return 2\n"
        )
        template = Path(__file__).parent / name
        shutil.copyfile(template / "before.py", root / "sample/work.py")
        contract_path = "docs/architecture/contract.json"
        (root / "docs/architecture").mkdir(parents=True)
        _json(root / contract_path, minimal_contract(contract_path))
        (root / "archkeel.toml").write_text(
            f'[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "{contract_path}"\n'
        )
        (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
        _git(root, "add", ".")
        _git(root, "commit", "-q", "-m", "accepted code")
        accepted_commit = _git(root, "rev-parse", "HEAD")
        report_path = output / (case + "-accepted.json")
        command(
            [
                "report",
                "--root",
                str(root),
                "--output",
                str(report_path),
            ],
            expected=0,
            label=case + "-report",
        )
        accepted = parse_observation(decode_canonical_model(json.loads(report_path.read_bytes())))
        lock = {
            "schema_version": "1.0.0",
            "accepted_commit": accepted_commit,
            "observation_digest": sha256_bytes(canonical_report_bytes(accepted)),
            "config_digest": sha256_bytes((root / "archkeel.toml").read_bytes()),
            "checker_digest": package_digest(),
            "measurements": asdict(measure_python_ratchets(accepted)),
            "approval_ref": "fixture-only:simulated-host-approval",
        }
        lock_bytes = _json(root / "architecture-accepted.json", lock)
        _git(root, "add", "architecture-accepted.json")
        _git(root, "commit", "-q", "-m", "CI accepted lock")
        baseline = _git(root, "rev-parse", "HEAD")
        _git(root, "push", "-q", "origin", "main")
        _git(root, "checkout", "-q", "-b", "candidate")

        # Private planning is allowed; publication still precedes submission in A and C.
        preview = output / (case + "-preview")
        shutil.copytree(root / "sample", preview / "sample")
        shutil.copyfile(root / "pyproject.toml", preview / "pyproject.toml")
        shutil.copyfile(template / "after.py", preview / "sample/work.py")
        config = load_config(root)
        planned_result = observe(
            preview,
            roots=config.roots,
            namespace=config.namespace,
            contract=config.contract,
            git_head="f" * 40,
            dirty=False,
            contract_root=root,
        )
        assert planned_result.exit_code == 0, planned_result.diagnostics
        planned = planned_result.observation
        assert planned is not None
        delta = build_architecture_delta(
            accepted,
            planned,
            baseline_digest=lock["observation_digest"],
            head_digest=sha256_bytes(canonical_report_bytes(planned)),
            checker_digest=package_digest(),
        )
        expectation = {
            "schema_version": EXPECTATION_SCHEMA_VERSION,
            "evidence_class": "HYPOTHESIS",
            "accepted_digest": sha256_bytes(lock_bytes),
            "baseline_commit": baseline,
            "checker_digest": package_digest(),
            "analyzer_digest": accepted.analyzer.code_digest,
            "contract_digest": accepted.contract.digest,
            "baseline_digest": lock["observation_digest"],
            "selected_changes": [
                {
                    key: change[key]
                    for key in ("dimension", "change", "fingerprint", "before_count", "after_count")
                }
                for change in delta_payload(delta)["semantic_changes"]
            ],
            "guardrails": dict.fromkeys(GUARDRAIL_KEYS, True),
        }
        expectation_bytes = _json(root / "expectation.json", expectation)
        _git(root, "add", "expectation.json")
        _git(root, "commit", "-q", "-m", "declare candidate")
        declared = _git(root, "rev-parse", "HEAD")
        if case != "B":
            _git(root, "push", "-q", "origin", "candidate")
        shutil.copyfile(template / "after.py", root / "sample/work.py")
        _git(root, "add", "sample/work.py")
        _git(root, "commit", "-q", "-m", "candidate refactor")
        head = _git(root, "rev-parse", "HEAD")
        _git(root, "push", "-q", "origin", "candidate")
        if case == "B":
            _git(root, "push", "-q", "origin", f"{declared}:refs/heads/expectation")
        host_path = output / (case + "-host-records.json")
        _json(
            host_path,
            [
                {
                    "sha": declared,
                    "event": "expectation_published",
                    "timestamp": "2026-09-13T10:02:00Z" if case == "B" else "2026-09-13T10:00:00Z",
                },
                {"sha": head, "event": "candidate_submitted", "timestamp": "2026-09-13T10:01:00Z"},
            ],
        )
        args = [
            "check",
            "--root",
            str(root),
            "--baseline",
            baseline,
            "--expectation-commit",
            declared,
            "--head",
            head,
            "--expected",
            "expectation.json",
            "--expected-digest",
            sha256_bytes(expectation_bytes),
            "--branch",
            "candidate",
            "--accepted-branch",
            "main",
        ]
        result = command(
            [*args, "--host-records", str(host_path)], expected=code, label=case + "-check"
        )
        tracked = _git(root, "ls-files").splitlines()
        assert len(tracked) < 10
        results[case] = {
            "exit_code": code,
            "tracked_files": len(tracked),
            "git_predicate": result["git_predicate"],
            "observation_complete": result["observation_complete"],
            "declared_rules": result["declared_rules"],
            "expectation_fulfilled": result["expectation_fulfilled"],
            "host_order": result["host_order"],
            "failures": result["failures"],
            "ratchets": result["delta"]["ratchets"],
        }
        if case == "B":
            missing = command(args, expected=2, label="B-missing-host")
            results["B-missing-host"] = {
                "exit_code": missing["exit_code"],
                "diagnostics": missing["diagnostics"],
            }
    assert results["A"]["host_order"] == "PASS" and all(
        "regression check failed" in item for item in results["A"]["failures"]
    )
    assert results["B"]["failures"] == [
        "expectation was not published before the first candidate submission"
    ]
    assert results["C"]["expectation_fulfilled"] == "PASS"
    _json(output / "results.json", results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or Path(mkdtemp(prefix="archkeel-fixtures-"))
    reproduce(destination)
    print(destination / "results.json")
