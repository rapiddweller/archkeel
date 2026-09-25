# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-104 (#150): a contract the `--against` revision lacks is introduced, not unreadable."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG as SHOP_CONFIG
from test_architecture_demo import _prepare_repo
from test_baseline import PROBE

from archkeel.analyzer import observe
from archkeel.check.git import MissingBlobError, read_blob
from archkeel.check.validation import run_validate
from archkeel.cli.config import load_config
from archkeel.ir.codec import baseline_bytes, decode_json, parse_amendment
from fixtures.demo_catalog_dart import DART_FIXTURE_DIR
from fixtures.demo_catalog_support import FIXTURE_DIR, apply_overlay, contract_measurement_budgets


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=root, text=True
    ).strip()


def _base(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD")


def _mobile_scope(tmp_path: Path, base_files: dict[str, str | None] | None = None) -> Path:
    """The merge request #150 describes: the shop sample is committed, and a Flutter-style
    package with its own archkeel.toml and contract is added under mobile/."""
    root = _prepare_repo(tmp_path, base_files or {})
    shutil.rmtree(root / "mobile", ignore_errors=True)
    shutil.copytree(DART_FIXTURE_DIR, root / "mobile")
    return root / "mobile"


def _introduced(path: str, against: str) -> tuple[int, tuple[str, ...]]:
    return 1, (f"contract introduced: {path} does not exist at {against}",)


def test_a_missing_blob_names_its_repository_path_below_the_root(tmp_path: Path) -> None:
    mobile = _mobile_scope(tmp_path)

    with pytest.raises(MissingBlobError) as raised:
        read_blob(mobile, _base(mobile), "architecture-contract.json")

    assert raised.value.path == "mobile/architecture-contract.json"
    assert str(raised.value) == "missing regular Git blob: mobile/architecture-contract.json"


def test_a_scope_directory_starting_with_a_colon_is_looked_up_like_any_other(
    tmp_path: Path,
) -> None:
    """The lookup stays relative to --root: `:app/...` as a pathspec would be Git magic."""
    root = _prepare_repo(tmp_path, {})
    shutil.copytree(DART_FIXTURE_DIR, root / ":app")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "app")
    scope = root / ":app"

    result, _ = run_validate(scope, load_config(scope), observe, against=_base(root))

    assert (result.exit_code, result.failures, result.diagnostics) == (0, (), ())


def test_a_scope_directory_that_is_not_utf8_reads_and_names_its_blobs(tmp_path: Path) -> None:
    """Only a message needs the directory's name, and a name no reader decodes cannot stop it."""
    root = _prepare_repo(tmp_path, {})
    scope = root / os.fsdecode(b"app\xff")
    shutil.copytree(DART_FIXTURE_DIR, scope)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "app")
    base = _base(root)

    assert (
        read_blob(scope, base, "architecture-contract.json")
        == (DART_FIXTURE_DIR / "architecture-contract.json").read_bytes()
    )
    with pytest.raises(MissingBlobError) as raised:
        read_blob(scope, base, "absent.json")
    assert raised.value.path == "app�/absent.json"


def test_a_second_contract_the_revision_lacks_is_one_introduction(tmp_path: Path) -> None:
    mobile = _mobile_scope(tmp_path)
    base = _base(mobile)

    result, _ = run_validate(mobile, load_config(mobile), observe, against=base)

    assert result.diagnostics == ()
    assert (result.exit_code, result.failures) == _introduced(
        "mobile/architecture-contract.json", base
    )


def test_an_introduced_contract_passes_only_with_its_own_amendment(tmp_path: Path) -> None:
    mobile = _mobile_scope(tmp_path)
    base = _base(mobile)
    config = load_config(mobile)
    amendment = mobile / "introduction.json"

    written, files = run_validate(
        mobile,
        config,
        observe,
        against=base,
        amendment=amendment,
        write_amendment=True,
        decided_by="Jordan (architect)",
        rationale="The mobile app gets its own contract.",
    )
    assert (written.exit_code, written.failures) == (0, ())
    amendment.write_bytes(files[str(amendment)])
    # The before side is no contract at this path: a NUL begins no canonical contract.
    record = parse_amendment(decode_json(amendment.read_bytes()))
    absent = b"\0no contract at mobile/architecture-contract.json"
    assert record.before_digest == hashlib.sha256(absent).hexdigest()

    result, _ = run_validate(mobile, config, observe, against=base, amendment=amendment)
    assert (result.exit_code, result.failures) == (0, ())

    # The record binds this contract: a different one introduced under it still fails.
    contract = json.loads((mobile / "architecture-contract.json").read_text())
    contract["rules"][0]["rationale"] = "A different contract than the one decided."
    (mobile / "architecture-contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    changed, _ = run_validate(mobile, config, observe, against=base, amendment=amendment)
    assert (changed.exit_code, changed.failures) == _introduced(
        "mobile/architecture-contract.json", base
    )


def test_an_introduction_record_does_not_verify_the_contract_moved_elsewhere(
    tmp_path: Path,
) -> None:
    """A record binds the path it introduced: replayed for the same contract moved to a path
    the revision lacks, after that revision narrowed it, it must not verify the move."""
    mobile = _mobile_scope(tmp_path)
    root = mobile.parent
    record = mobile / "introduced.json"
    _, files = run_validate(
        mobile,
        load_config(mobile),
        observe,
        against=_base(root),
        amendment=record,
        write_amendment=True,
        decided_by="Jordan (architect)",
        rationale="The mobile app gets its own contract.",
    )
    record.write_bytes(files[str(record)])
    decided = (mobile / "architecture-contract.json").read_text()
    narrowing = {
        "id": "DEP-PRESENTATION-NO-DART-IO",
        "kind": "forbidden_dependency",
        "source": "shop.presentation",
        "target": "dart.io",
        "include_type_checking": True,
        "rationale": "Widgets never reach the platform directly.",
        "provenance": ["docs/architecture/shop.md"],
        "decided_by": "architect",
    }
    contract = json.loads(decided)
    contract["rules"].append(narrowing)
    (mobile / "architecture-contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "mobile contract, narrowed")
    narrowed = _base(root)
    # The change drops the narrowing by moving the decided contract to a new path.
    (mobile / "architecture-contract.json").unlink()
    (mobile / "policy").mkdir()
    (mobile / "policy/contract.json").write_text(decided)
    toml = mobile / "archkeel.toml"
    toml.write_text(toml.read_text().replace("architecture-contract.json", "policy/contract.json"))

    result, _ = run_validate(
        mobile, load_config(mobile), observe, against=narrowed, amendment=record
    )

    assert result.diagnostics == ()
    assert (result.exit_code, result.failures) == _introduced(
        "mobile/policy/contract.json", narrowed
    )


def test_a_moved_contract_is_introduced_not_passed(tmp_path: Path) -> None:
    """A new contract path must not bypass the widening gate: the old rules are not compared."""
    root = _prepare_repo(tmp_path, {})
    base = _base(root)
    (root / "contracts").mkdir()
    (root / "architecture-contract.json").rename(root / "contracts/shop.json")
    config = replace(SHOP_CONFIG, contract="contracts/shop.json")

    result, _ = run_validate(root, config, observe, against=base)

    assert result.diagnostics == ()
    assert (result.exit_code, result.failures) == _introduced("contracts/shop.json", base)


def test_a_moved_contract_still_compares_the_baseline_the_revision_holds(tmp_path: Path) -> None:
    """Moving the contract must not hide a baseline padded in the same change."""
    root = _prepare_repo(tmp_path, {"known-violations.json": baseline_bytes(()).decode()})
    base = _base(root)
    (root / "contracts").mkdir()
    (root / "architecture-contract.json").rename(root / "contracts/shop.json")
    apply_overlay(root, {"shop/model/probe.py": PROBE})
    config = replace(SHOP_CONFIG, contract="contracts/shop.json")
    baseline = root / "known-violations.json"
    _, files = run_validate(
        root, config, observe, baseline=baseline, write_baseline=True, accept_new=True
    )
    baseline.write_bytes(files[str(baseline)])

    result, _ = run_validate(root, config, observe, against=base, baseline=baseline)

    assert result.diagnostics == ()
    assert (result.exit_code, result.failures) == (
        1,
        (
            f"contract introduced: contracts/shop.json does not exist at {base}",
            "baseline entry widened: CONSTRUCT-NO-DYNAMIC | shop.model.probe.read "
            "(1 now, 0 before)",
        ),
    )


def test_a_configuration_the_revision_lacks_is_never_read_there(tmp_path: Path) -> None:
    """AD-101's second scope arrives with its configuration: only its contract path matters."""
    test_scope = {"archkeel-tests.toml": None, "tests/architecture-contract.json": None}
    root = _prepare_repo(tmp_path, test_scope)
    base = _base(root)
    apply_overlay(root, {path: (FIXTURE_DIR / path).read_text() for path in test_scope})

    result, _ = run_validate(root, load_config(root, "archkeel-tests.toml"), observe, against=base)

    assert result.diagnostics == ()
    assert (result.exit_code, result.failures) == _introduced(
        "tests/architecture-contract.json", base
    )


def test_a_baseline_introduced_with_its_contract_adds_no_widening(tmp_path: Path) -> None:
    """Every entry of a baseline the revision lacks is new; the introduction already says so."""
    root = _prepare_repo(tmp_path, {"architecture-contract.json": None})
    base = _base(root)
    apply_overlay(
        root,
        {
            "architecture-contract.json": contract_measurement_budgets("calls_unresolved"),
            "shop/model/probe.py": PROBE,
        },
    )
    baseline = root / "known-violations.json"
    _, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)
    baseline.write_bytes(files[str(baseline)])

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base, baseline=baseline)

    assert result.diagnostics == ()
    assert (result.exit_code, result.failures) == _introduced("architecture-contract.json", base)
    # No second scan names call sites against a revision that has no contract to scan under.
    assert (result.unresolved_call_changes, result.unresolved_call_note) == (None, None)


def test_a_contract_path_the_revision_holds_as_a_tree_stays_against_invalid(
    tmp_path: Path,
) -> None:
    """Only a missing blob is an introduction; one Git cannot hand over is still exit 2."""
    mobile = _mobile_scope(tmp_path, {"mobile/architecture-contract.json/README": "not a file\n"})

    result, _ = run_validate(mobile, load_config(mobile), observe, against=_base(mobile))

    assert (result.exit_code, result.failures) == (2, ())
    assert [(item.code, item.unknown_claim) for item in result.diagnostics] == [
        (
            "against.invalid",
            "The compared revision cannot be read: expected a regular Git blob: "
            "mobile/architecture-contract.json",
        )
    ]


def test_a_baseline_the_revision_holds_as_a_tree_stays_against_invalid(tmp_path: Path) -> None:
    """A missing baseline is no prior debt; one Git cannot hand over is not silently empty."""
    root = _prepare_repo(tmp_path, {"known-violations.json/README": "not a file\n"})
    base = _base(root)
    shutil.rmtree(root / "known-violations.json")
    baseline = root / "known-violations.json"
    _, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)
    baseline.write_bytes(files[str(baseline)])

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base, baseline=baseline)

    assert (result.exit_code, result.failures) == (2, ())
    assert [(item.code, item.unknown_claim) for item in result.diagnostics] == [
        (
            "against.invalid",
            "The compared revision cannot be read: expected a regular Git blob: "
            "known-violations.json",
        )
    ]


def test_a_baseline_the_revision_lacks_is_still_no_prior_debt(tmp_path: Path) -> None:
    """The contract exists there, so its baseline's absence means nothing was accepted yet."""
    root = _prepare_repo(tmp_path, {"shop/model/probe.py": PROBE})
    base = _base(root)
    baseline = root / "known-violations.json"
    _, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)
    baseline.write_bytes(files[str(baseline)])

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base, baseline=baseline)

    assert (result.exit_code, result.failures) == (
        1,
        ("baseline entry widened: CONSTRUCT-NO-DYNAMIC | shop.model.probe.read (1 now, 0 before)",),
    )
