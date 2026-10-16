# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Contract schema identity is nominal; historical wire versions stay exact."""

from enum import StrEnum
from typing import get_type_hints

import pytest

from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.codec_contract import ContractVersionError
from archkeel.ir.model import ArchitectureContract

VERSIONS = (
    "2.1.0", "2.2.0", "2.3.0", "3.0.0", "3.1.0",
    "3.2.0", "3.3.0", "3.4.0", "3.5.0", "3.6.0",
)


@pytest.mark.parametrize("version", VERSIONS)
def test_parser_normalizes_each_historical_version_to_a_nominal_owner(version):
    raw = {"schema_version": version, "components": [], "rules": []}
    contract = parse_contract(raw)
    assert isinstance(contract.schema_version, StrEnum)
    assert str(contract.schema_version) == version
    assert contract_bytes(contract) == (
        '{"schema_version":"' + version + '","components":[],"rules":[]}\n'
    ).encode()
    assert parse_contract(raw) == contract


@pytest.mark.parametrize("version", VERSIONS)
def test_direct_valid_legacy_version_is_normalized_at_model_ingress(version):
    contract = ArchitectureContract(version, (), ())
    assert isinstance(contract.schema_version, StrEnum)
    assert str(contract.schema_version) == version


def test_contract_version_field_has_a_concrete_nominal_type():
    annotation = get_type_hints(ArchitectureContract)["schema_version"]
    assert isinstance(annotation, type) and issubclass(annotation, StrEnum)


@pytest.mark.parametrize("invalid", [None, True, 1, {}, [], "", "2.0.0", "3.7.0"])
def test_parser_keeps_rejecting_unsupported_or_nontext_versions(invalid):
    with pytest.raises(ContractVersionError):
        parse_contract({"schema_version": invalid, "components": [], "rules": []})
