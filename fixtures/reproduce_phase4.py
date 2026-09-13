"""Run exactly the dispatch and post-hoc expectation counterexamples."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


BASELINE = '''from typing import Literal


def up(value: int) -> int:
    return value + 1


def down(value: int) -> int:
    return value - 1


def apply(key: Literal["up", "down"], value: int) -> int:
    if key == "up":
        return up(value)
    return down(value)
'''

DISPATCH = '''from typing import Literal


def up(value: int) -> int:
    return value + 1


def down(value: int) -> int:
    return value - 1


def apply(key: Literal["up", "down"], value: int) -> int:
    handlers = {"up": up, "down": down}
    return handlers[key](value)
'''

MAKEFILE = '''PYTHON ?= python3

.PHONY: architecture-check
architecture-check:
	$(PYTHON) -B -c 'from pathlib import Path; from script.architecture.__main__ import main; raise SystemExit(main(root=Path.cwd()))' check --baseline "$(BASELINE)" --head "$(HEAD)" --expected "$(EXPECTED)" --expected-digest "$(EXPECTED_DIGEST)"
'''


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", required=True, type=Path)
    args = parser.parse_args()
    framework = args.framework.resolve()
    sys.path.insert(0, str(framework))
    from script.architecture.delta import _fingerprint, generate_delta
    from script.architecture.expectation import GUARDRAIL_KEYS, evaluate_expectation, load_expectation
    from script.architecture.model import analyzer_code_digest, canonical_report_bytes
    from script.architecture.report import analyze_snapshot

    output = Path(tempfile.mkdtemp(prefix="architecture-phase4-", dir="/private/tmp"))
    environment = dict(os.environ, PYTHONPATH=str(framework), PYTHONDONTWRITEBYTECODE="1")
    framework_status_before = subprocess.check_output(["git", "status", "--short"], cwd=framework, text=True)
    framework_digest = analyzer_code_digest(framework)
    results = {}

    for case in ("A", "B"):
        case_dir = output / case
        root = case_dir / "fixture"
        root.mkdir(parents=True)
        artifacts = case_dir / "artifacts"
        artifacts.mkdir()
        (root / "script").symlink_to(framework / "script", target_is_directory=True)
        (root / "test-artifacts").symlink_to(artifacts, target_is_directory=True)
        source = root / "datamimic_ee/demo.py"
        source.parent.mkdir()
        source.write_text(BASELINE)
        (root / "ARCHITECTURE.md").write_text(
            "Synthetic fixture only. Valid dispatch keys: up, down.\n"
            "demo must not import datamimic_ee.transport.\n"
        )
        (root / "Makefile").write_text(MAKEFILE)
        contract_path = root / "docs/architecture/architecture-contract.json"
        contract_path.parent.mkdir(parents=True)
        provenance = ["ARCHITECTURE.md"]
        contract = {
            "schema_version": "1.1.0",
            "capabilities": [{"id": "CAP-DEMO", "name": "DEMO", "label": "Demo", "review_order": 1, "provenance": provenance}],
            "components": [{"id": "COMP-DEMO", "label": "Demo", "role": "component", "capability_id": "CAP-DEMO", "packages": ["datamimic_ee.demo"], "responsibilities": ["Integer transformation"], "forbidden_responsibilities": ["Transport"], "provenance": provenance}],
            "review_scopes": [], "public_api": ["datamimic_ee.demo.apply"],
            "public_api_provenance": provenance, "public_commands": [],
            "context_roots": [], "context_roots_provenance": provenance,
            "paths": [], "spot_owners": [],
            "rules": [{"id": "DEP-DEMO-NO-TRANSPORT", "kind": "forbidden_dependency", "source": "datamimic_ee.demo", "target": "datamimic_ee.transport", "include_type_checking": True, "rationale": "Transformation owns no transport.", "provenance": provenance}],
        }
        write_json(contract_path, contract)
        events = []

        def event(name, **details):
            events.append({"step": len(events) + 1, "event": name, "monotonic_ns": time.monotonic_ns(), **details})

        def git(*arguments):
            return subprocess.check_output(["git", *arguments], cwd=root, env=environment, text=True).strip()

        git("init", "-q", "-b", "feat/phase4")
        git("config", "user.name", "Architecture Fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "commit.gpgsign", "false")
        tracked = ["ARCHITECTURE.md", "Makefile", "datamimic_ee/demo.py", "docs/architecture/architecture-contract.json"]
        git("add", "--", *tracked)
        git("commit", "-qm", "Add direct-call fixture")
        baseline_sha = git("rev-parse", "HEAD")
        event("baseline_committed", sha=baseline_sha)
        baseline_model, baseline_exit = analyze_snapshot(root, git_head=baseline_sha, dirty=False)
        assert baseline_exit == 0
        assert baseline_model["analyzer"]["code_digest"] == framework_digest
        baseline_digest = hashlib.sha256(canonical_report_bytes(baseline_model)).hexdigest()
        write_json(case_dir / "baseline-decoded.json", baseline_model)
        expectation_path = root / "expectation.json"

        def write_expectation(selected_changes):
            payload = {
                "schema_version": "1.0.0", "evidence_class": "HYPOTHESIS",
                "analyzer_digest": framework_digest,
                "contract_digest": baseline_model["contract"]["digest"],
                "baseline_digest": baseline_digest,
                "selected_changes": selected_changes,
                "guardrails": dict.fromkeys(GUARDRAIL_KEYS, True),
            }
            write_json(expectation_path, payload)
            digest = hashlib.sha256(expectation_path.read_bytes()).hexdigest()
            event("expectation_written", sha256=digest)
            return digest

        if case == "A":
            # Predict the coverage-field change before changing fixture code.
            fingerprint = _fingerprint({"key": "calls_unresolved"})
            expectation_digest = write_expectation([{
                "dimension": "coverage", "change": "changed", "fingerprint": fingerprint,
                "before_count": 1, "after_count": 1,
            }])

        source.write_text(DISPATCH)
        event("dispatch_code_written")
        git("add", "--", "datamimic_ee/demo.py")
        git("commit", "-qm", "Replace direct calls with dispatch")
        head_sha = git("rev-parse", "HEAD")
        event("head_committed", sha=head_sha)
        (case_dir / "code.diff").write_text(git("diff", baseline_sha, head_sha, "--", "datamimic_ee/demo.py") + "\n")
        if case == "B":
            assert not expectation_path.exists()
            assert "expectation.json" not in git("ls-tree", "-r", "--name-only", head_sha).splitlines()
            event("expectation_absent_after_head_commit", exists=False, tracked_in_head=False)

        delta, delta_exit, _ = generate_delta(root, baseline_sha, head_sha)
        assert delta_exit == 0
        assert delta["provenance"]["baseline_digest"] == baseline_digest
        event("delta_generated", exit_code=delta_exit)
        if case == "B":
            expectation_digest = write_expectation([
                {key: change[key] for key in ("dimension", "change", "fingerprint", "before_count", "after_count")}
                for change in delta["semantic_changes"]
            ])

        expectation = load_expectation(expectation_path, expected_digest=expectation_digest)
        evaluation = evaluate_expectation(delta, expectation)
        assert evaluation.passed and not evaluation.failures, evaluation.failures
        command = ["make", "architecture-check", f"PYTHON={sys.executable}", f"BASELINE={baseline_sha}", f"HEAD={head_sha}", "EXPECTED=expectation.json", f"EXPECTED_DIGEST={expectation_digest}"]
        completed = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True)
        (case_dir / "check.stdout").write_text(completed.stdout)
        (case_dir / "check.stderr").write_text(completed.stderr)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        event("architecture_check_completed", exit_code=completed.returncode)

        head_model, head_exit = analyze_snapshot(root, git_head=head_sha, dirty=False)
        assert head_exit == 0
        write_json(case_dir / "head-decoded.json", head_model)
        before, after = baseline_model["coverage"], head_model["coverage"]
        assert before["files_discovered"] == after["files_discovered"] == 1
        assert before["calls_analyzed"] == 2 and before["calls_unresolved"] == 0
        assert after["calls_analyzed"] == 1 and after["calls_unresolved"] == 1
        assert after["calls_unresolved"] / after["calls_analyzed"] > before["calls_unresolved"] / before["calls_analyzed"]
        old_namespace, new_namespace = {}, {}
        exec(BASELINE, old_namespace)
        exec(DISPATCH, new_namespace)
        behavior_cases = [(key, value) for key in ("up", "down") for value in (-1, 0, 1)]
        for key, value in behavior_cases:
            assert old_namespace["apply"](key, value) == new_namespace["apply"](key, value)

        entries = []
        for parent, directories, files in os.walk(root, followlinks=False):
            directories[:] = [name for name in directories if name != ".git"]
            entries.extend(str((Path(parent) / name).relative_to(root)) for name in files)
            entries.extend(str((Path(parent) / name).relative_to(root)) for name in directories if (Path(parent) / name).is_symlink())
        assert len(entries) < 10
        event_names = [entry["event"] for entry in events]
        if case == "A":
            assert event_names.index("expectation_written") < event_names.index("dispatch_code_written")
        else:
            assert event_names.index("head_committed") < event_names.index("delta_generated") < event_names.index("expectation_written")
        write_json(case_dir / "events.json", events)
        counters = {name: {"before": dim["before_count"], "after": dim["after_count"], "added": len(dim["added"]), "changed": len(dim["changed"])} for name, dim in delta["dimensions"].items()}
        results[case] = {
            "verification": "LOCAL VERIFIED", "fixture_root": str(root),
            "fixture_entries_excluding_git_and_external_symlink_targets": sorted(entries),
            "fixture_entry_count": len(entries), "tracked_fixture_files": len(git("ls-files").splitlines()),
            "scanned_python_files_before": before["files_parsed"], "scanned_python_files_after": after["files_parsed"],
            "calls_total_before": before["calls_analyzed"], "calls_unresolved_before": before["calls_unresolved"],
            "unresolved_ratio_before": before["calls_unresolved"] / before["calls_analyzed"],
            "calls_total_after": after["calls_analyzed"], "calls_unresolved_after": after["calls_unresolved"],
            "unresolved_ratio_after": after["calls_unresolved"] / after["calls_analyzed"],
            "guardrails": dict.fromkeys(GUARDRAIL_KEYS, "PASS"),
            "guardrail_evidence": "Unmodified evaluator returned no failures; all fixed guardrails are mandatory and enabled.",
            "dimension_counts": counters, "delta_coverage": delta["coverage"]["status"],
            "check_exit_code": completed.returncode, "check_failures": list(evaluation.failures),
            "expectation_written_before_code_change": case == "A",
            "selected_change_count": len(expectation.selected_changes),
            "behavior_cases_compared": len(behavior_cases),
            "baseline_sha": baseline_sha, "head_sha": head_sha,
            "analyzer_digest": framework_digest, "expectation_digest": expectation_digest,
        }
        write_json(case_dir / "result.json", results[case])

    framework_status_after = subprocess.check_output(["git", "status", "--short"], cwd=framework, text=True)
    assert framework_status_before == framework_status_after
    assert analyzer_code_digest(framework) == framework_digest
    write_json(output / "results.json", {"framework": str(framework), "framework_status_unchanged": True, "framework_status": framework_status_after, "cases": results})
    print(json.dumps({"output": str(output), "A": "LOCAL VERIFIED", "B": "LOCAL VERIFIED"}))


if __name__ == "__main__":
    main()
