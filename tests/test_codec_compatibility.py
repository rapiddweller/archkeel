# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The codec facade retains eager imports and the original callable identities."""

import importlib
import subprocess
import sys

import pytest

from archkeel.ir import codec, facts_codec, model

OWNERS = {
    "wire": ("canonical_json_bytes", "decode_json", "value_bytes"),
    "governance": (
        "parse_measurements",
        "parse_lock",
        "parse_validation_baseline",
        "parse_baseline",
        "baseline_bytes",
        "baseline_digest",
        "absent_baseline_digest",
        "parse_amendment",
        "amendment_bytes",
    ),
    "contract": (
        "CONTRACT_SCHEMA_VERSION",
        "ContractVersionError",
        "parse_contract",
        "parse_dependency_selector",
        "contract_bytes",
        "contract_digest",
        "absent_contract_digest",
        "parse_required_component",
        "_rule_payload",
    ),
    "inside": ("contract_provenance_paths", "load_inside_contract_tree", "declaration_paths"),
    "observation": (
        "parse_observation",
        "observation_payload",
        "encode_canonical_model",
        "decode_canonical_model",
        "canonical_report_bytes",
    ),
    "delta": ("parse_delta", "delta_payload"),
    "result": ("result_payload", "result_bytes", "_architecture_component_payload"),
}


@pytest.mark.parametrize(("owner", "names"), OWNERS.items())
def test_facade_reexports_the_same_implementation_objects(owner, names):
    implementation = importlib.import_module(f"archkeel.ir.codec_{owner}")
    for name in names:
        assert getattr(codec, name) is getattr(implementation, name)


def test_existing_value_and_fact_aliases_keep_their_owners():
    for name in (
        "RawJson",
        "ContractInputError",
        "InsideContractIssue",
        "InsideContractMount",
        "InsideContractTree",
    ):
        assert getattr(codec, name) is getattr(model, name)
    assert codec.parse_record is facts_codec.parse_record
    assert codec.parse_evidence is facts_codec.parse_evidence
    assert not hasattr(codec, "load_observation")


def test_star_import_retains_the_declared_public_bindings():
    expected = {name for names in OWNERS.values() for name in names if not name.startswith("_")} | {
        "RawJson",
        "ContractInputError",
        "InsideContractIssue",
        "InsideContractMount",
        "InsideContractTree",
        "parse_record",
        "parse_evidence",
    }
    namespace = {}
    exec("from archkeel.ir.codec import *", namespace)
    assert namespace.keys() - {"__builtins__"} == expected
    for name in expected:
        assert namespace[name] is getattr(codec, name)


@pytest.mark.parametrize("facade_first", [False, True])
def test_eager_imports_work_from_either_side_of_the_facade(facade_first):
    owners = [f"archkeel.ir.codec_{name}" for name in reversed(OWNERS)]
    modules = ["archkeel.ir.codec", *owners] if facade_first else [*owners, "archkeel.ir.codec"]
    script = (
        "import importlib\n"
        f"modules = [importlib.import_module(name) for name in {modules!r}]\n"
        "from archkeel.ir import codec, codec_contract, codec_result\n"
        "assert codec.ContractVersionError is codec_contract.ContractVersionError\n"
        "assert codec.result_bytes is codec_result.result_bytes\n"
        "try:\n"
        "    codec.parse_contract({'schema_version':'unsupported', 'components':[], 'rules':[]})\n"
        "except codec.ContractVersionError as error:\n"
        "    assert error.actual == 'unsupported'\n"
        "    assert str(error) == \"contract.schema_version 'unsupported' is not 2.1.0\"\n"
        "else:\n"
        "    raise AssertionError('unsupported version accepted')\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
