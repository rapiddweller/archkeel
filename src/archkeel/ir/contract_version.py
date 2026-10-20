# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Own contract schema identities and their shared feature availability."""

from enum import StrEnum
from typing import Final

CONTRACT_SCHEMA_VERSION: Final = "2.1.0"


class ContractFeature(StrEnum):
    CALL_OWNER = "call_owner"
    UML = "uml"
    LAYERS = "layers"
    ALIAS_BODY = "alias_body"
    KEY_ALIAS_BODY = "key_alias_body"
    LITERAL_MAPPING_ARM = "literal_mapping_arm"
    NATIVE_MAPPING = "native_mapping"
    MODULE_SELECTORS = "module_selectors"
    IMPORT_NAMESPACES = "import_namespaces"
    MODULE_OBJECT_GRANTS = "module_object_grants"


class ContractVersion(StrEnum):
    V2_1 = CONTRACT_SCHEMA_VERSION
    V2_2 = "2.2.0"
    V2_3 = "2.3.0"
    V3_0 = "3.0.0"
    V3_1 = "3.1.0"
    V3_2 = "3.2.0"
    V3_3 = "3.3.0"
    V3_4 = "3.4.0"
    V3_5 = "3.5.0"
    V3_6 = "3.6.0"
    V3_7 = "3.7.0"


# Declaration order is the supported contract evolution order.
_VERSION_RANK: dict[ContractVersion, int] = {
    version: position for position, version in enumerate(ContractVersion)
}
_FEATURE_START: dict[ContractFeature, ContractVersion] = {
    ContractFeature.CALL_OWNER: ContractVersion.V3_7,
    ContractFeature.UML: ContractVersion.V2_2,
    ContractFeature.LAYERS: ContractVersion.V2_3,
    ContractFeature.ALIAS_BODY: ContractVersion.V3_0,
    ContractFeature.KEY_ALIAS_BODY: ContractVersion.V3_1,
    ContractFeature.LITERAL_MAPPING_ARM: ContractVersion.V3_2,
    ContractFeature.NATIVE_MAPPING: ContractVersion.V3_3,
    ContractFeature.MODULE_SELECTORS: ContractVersion.V3_4,
    ContractFeature.IMPORT_NAMESPACES: ContractVersion.V3_5,
    ContractFeature.MODULE_OBJECT_GRANTS: ContractVersion.V3_6,
}


def supports_feature(version: ContractVersion, feature: ContractFeature) -> bool:
    """Read and write use the same feature introduction policy."""
    return _VERSION_RANK[version] >= _VERSION_RANK[_FEATURE_START[feature]]
