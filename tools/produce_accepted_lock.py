"""One-off reviewed CI bootstrap; approval is supplied by the owner, not inferred."""

import argparse
import json
import os
import platform
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from archkeel.analyzer import observe
from archkeel.check.expectation import sha256_bytes
from archkeel.check.git import git_bytes, read_blob
from archkeel.check.run import inspect_observation, observe_revision
from archkeel.cli.config import load_check_config
from archkeel.ir.codec import canonical_report_bytes, parse_lock
from archkeel.ir.digest import package_digest
from archkeel.ir.host_records import validate_sha
from archkeel.ir.lock import LOCK_PATH, verify_observation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--accepted-commit", required=True)
    parser.add_argument("--approval-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    accepted = validate_sha(args.accepted_commit, "accepted_commit")
    if git_bytes(root, "rev-parse", "HEAD").decode().strip() != accepted:
        raise ValueError("checkout is not the approved source commit")
    if git_bytes(root, "status", "--porcelain"):
        raise ValueError("approved source checkout must be clean")
    config = load_check_config(root, accepted, accepted)
    if config.digest != sha256_bytes(read_blob(root, accepted, "archkeel.toml")):
        raise ValueError("configuration differs from the approved commit")
    result = observe_revision(observe, root, accepted, config, declared_at=accepted)
    if (
        result.observation is None
        or result.diagnostics
        or result.coverage is None
        or result.coverage.status != "PASS"
    ):
        raise ValueError("approved source could not be observed completely")
    model = result.observation
    measurements, declared = inspect_observation(model)
    if measurements.scalars.coverage_failures or measurements.scalars.violations:
        raise ValueError("this bootstrap requires complete coverage and zero violations")
    observation = canonical_report_bytes(model)
    data = {
        "schema_version": "1.0.0",
        "accepted_commit": accepted,
        "observation_digest": sha256_bytes(observation),
        "config_digest": config.digest,
        "checker_digest": package_digest(),
        "measurements": asdict(measurements),
        "approval_ref": args.approval_ref,
    }
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    lock = parse_lock(payload)
    verify_observation(
        lock, observation_digest=sha256_bytes(observation), measurements=measurements
    )
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / LOCK_PATH).write_bytes(payload)
    (args.output / "architecture.json").write_bytes(observation)
    proof = {
        "accepted_commit": accepted,
        "approval_ref": args.approval_ref,
        "declared_rules": declared,
        "python": platform.python_version(),
        "package_version": version("archkeel"),
        "checker_digest": lock.checker_digest,
        "config_digest": config.digest,
        "observation_digest": lock.observation_digest,
        "lock_sha256": sha256_bytes(payload),
        "producer_commit": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
    }
    (args.output / "proof.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main()
