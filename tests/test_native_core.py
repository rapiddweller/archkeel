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

import pytest
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


# A test build and the feature `harness` have the request kinds that carry a reply.
TEST_CFG = r"#\[cfg\(any\(test, feature = \"harness\"\)\)\]"


def _production_trust_sites() -> list[str]:
    """Each function of the core that names `Producer::Trusted` outside a test build.

    A module that `main.rs` declares under `#[cfg(any(test, feature = "harness"))]`, and a function
    that has that attribute, are not production code (#1095).
    """
    main = (ROOT / "native/core/src/main.rs").read_text()
    test_modules = set(re.findall(rf"{TEST_CFG}\s*mod (\w+);", main))
    found = []
    for path in sorted((ROOT / "native/core/src").glob("*.rs")):
        if path.name.endswith("_tests.rs") or path.stem in test_modules:
            continue
        function, test_only, attribute = "", False, False
        for line in path.read_text().splitlines():
            if match := re.match(r"\s*(?:pub\(crate\) )?fn (\w+)", line):
                function, test_only, attribute = match[1], attribute, False
            elif re.fullmatch(TEST_CFG, line.strip()):
                attribute = True
            elif not line.lstrip().startswith(("#[", "//")):
                attribute = False
            if "Producer::Trusted" in line and not line.lstrip().startswith("//") and not test_only:
                found.append(f"{path.name}::{function}")
    return found


def test_production_code_of_the_core_reaches_a_trusted_producer_in_one_function_only() -> None:
    """#1095: the scan request reaches trust only in `in_process`, because the core ran the
    collector itself (AD-406). The check and dual-run request kinds, which carry a reply, are
    compiled in test builds only."""
    assert _production_trust_sites() == ["scan.rs::in_process"]


@pytest.mark.parametrize("kind", ["dual-run", "check", "bogus"])
def test_the_release_core_has_no_request_kind_that_carries_a_reply(
    release_core: Path, kind: str
) -> None:
    done = subprocess.run(
        [str(release_core), kind], input=b"{}", capture_output=True, check=False, timeout=60
    )
    assert done.returncode == 2 and done.stdout == b""
    assert b"usage: archkeel-core scan" in done.stderr, done.stderr


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


def test_a_harness_core_names_itself_in_the_engine_of_its_frame(harness_core: Path) -> None:
    """#1095: the frame of a core that has the reply-carrying request kinds says so after its code
    digest. The request has no reply, so the frame names a gap (exit 3) and still has an engine."""
    request = {
        "protocol": "archkeel-dual-run-5",
        "case": "c",
        "root": "/r",
        "config": "archkeel.toml",
        "baseline": None,
        "collector_argv": None,
        "contracts": {"architecture-contract.json": "{}"},
        "reply": None,
        "sections": [],
        "namespace": "shop",
        "profile": "",
        "standard_library": [],
        "insides": [],
        "roots": [],
    }
    done = subprocess.run(
        [str(harness_core), "dual-run"],
        input=json.dumps(request).encode(),
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert done.returncode == 3, done.stderr
    engine = json.loads(done.stdout)["engine"]
    assert re.fullmatch(r"archkeel-core [0-9a-f]{64}\+harness", engine), engine


def test_one_environment_builds_the_shared_release_core() -> None:
    """#1182: a builder with another `ARCHKEEL_VERSION` relinks the core under a worker that runs
    it. Only `core_support.py` names the variable, and each builder of `native/target` uses it."""
    named = {
        path.name
        for path in (ROOT / "tests").glob("*.py")
        if "ARCHKEEL_VERSION" in path.read_text() and path.name != Path(__file__).name
    }
    assert named == {"core_support.py"}
    builders = {"core_support.py"}
    for name in builders:
        assert "build_environment()" in (ROOT / "tests" / name).read_text(), name
    # A test that runs `cargo build --release` for the core must be the one builder.
    for path in (ROOT / "tests").glob("*.py"):
        text = path.read_text()
        runs_cargo = bool(re.search(r'"build",\s*"--locked"', text)) and "--release" in text
        assert not runs_cargo or path.name in builders | {Path(__file__).name}, path.name
