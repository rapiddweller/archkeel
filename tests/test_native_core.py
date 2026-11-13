# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-432: the core binary decides, and the shell names it in four modules only.

The tests that compared the core with the Python checker went away with the Python checker. The
tests that stay read the core binary or the native sources and need no Python reference.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import rust_repository
from corpus_support import commit_tree
from native_rules_support import language_names

ROOT = Path(__file__).resolve().parents[1]


def test_a_configured_external_collector_is_refused_and_never_passes(
    tmp_path: Path, core_binary: Path
) -> None:
    """AD-388: the core cannot verify a collector that the project names, so it runs only its
    own. A config with `collector_argv` gives a typed refusal and exit 2, with no rule row."""
    root = rust_repository.repository(tmp_path, core_binary)
    with (root / "archkeel.toml").open("a") as config:
        config.write('collector_argv = ["./collector"]\n')
    commit_tree(root)
    for command in ("validate", "report"):
        code, result = rust_repository.outcome(root, command)
        assert code == 2, result
        assert result["status"] == "UNKNOWN"
        assert not result.get("frame", {}).get("rules")
        message = result["refusal"]["message"]
        assert "the run uses the configured collector ./collector" in message, result


def test_a_repeated_section_name_is_refused_before_any_row_is_built(
    core_binary: Path,
) -> None:
    """AD-374 review: a request that names one section many times made the core build its rows
    once for each name (9.56 GB for 200 names of `dependency_edges`). The binary refuses it."""
    request = {
        "protocol": "archkeel-dual-run-5",
        "case": "c",
        "root": "/r",
        "config": "archkeel.toml",
        "baseline": None,
        "collector_argv": None,
        "contracts": {"architecture-contract.json": "{}"},
        "reply": None,
        "sections": ["cycles", "modules", "cycles"],
        "namespace": "shop",
        "profile": "",
        "standard_library": [],
        "insides": [],
        "roots": [],
    }
    done = subprocess.run(
        [str(core_binary), "dual-run"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2
    assert done.stdout == ""
    assert "repeated section cycles" in done.stderr


def test_the_shell_names_the_core_in_four_modules_and_no_wheel_carries_it() -> None:
    """AD-432: the entry, its frame reader, its scan request and the binary lookup name the core.
    No wheel carries the core yet, so an installed package refuses with `core_binary_not_found`."""
    names = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src/archkeel").rglob("*.py")
        if "archkeel-core" in path.read_text() or "archkeel_core" in path.read_text()
    }
    assert names == {
        "src/archkeel/cli/core_only.py",
        "src/archkeel/cli/core_frame.py",
        "src/archkeel/cli/native_scan.py",
        "src/archkeel/cli/core_binary.py",
    }
    assert "archkeel-core" not in (ROOT / "native/hatch_build.py").read_text()


def test_the_core_reaches_a_trusted_producer_in_two_named_functions_only() -> None:
    """AD-390 point 2: the check request reaches trust only in `stage_one_shell_trust`, the dual
    run only in its `producer` (AD-388), and the scan request only in `in_process`, because the
    core ran the collector itself (AD-406). No other production code of the core names it."""
    found = []
    for path in sorted((ROOT / "native/core/src").glob("*.rs")):
        if path.name.endswith("_tests.rs"):
            continue
        function = ""
        for line in path.read_text().splitlines():
            if match := re.match(r"\s*(?:pub\(crate\) )?fn (\w+)", line):
                function = match[1]
            if "Producer::Trusted" in line and not line.lstrip().startswith("//"):
                found.append(f"{path.name}::{function}")
    assert found == [
        "check.rs::stage_one_shell_trust",
        "dual_run.rs::producer",
        "scan.rs::in_process",
    ]


def test_the_model_the_evaluator_and_the_core_name_no_language() -> None:
    """The no-language rule of design WP6-0 section B; the Rust profile has no rule kind that
    reads an identifier, so the check is here and not in the native contract.

    AD-382: the rule also reads `report` and each subdirectory. AD-381 renamed the last
    language names of the `report` doc comments, so the pin is empty."""
    assert language_names(ROOT / "native") == Counter()


def test_each_native_component_is_a_node_of_the_component_graph() -> None:
    """The graph of native.md is written by hand while the native scan has gaps
    (`archkeel validate --write-graph` refuses), so a new component must not go missing."""
    contract = json.loads((ROOT / "native/architecture-contract.json").read_text())
    page = (ROOT / "docs/architecture/native.md").read_text()
    block = page.split("<!-- archkeel-component-graph -->", 1)[1].split("```", 2)[1]
    nodes = set(re.findall(r'n_\d+\["([^"]+)"\]', block))
    assert {component["label"] for component in contract["components"]} <= nodes
    assert "n_2 --> n_31" in block
