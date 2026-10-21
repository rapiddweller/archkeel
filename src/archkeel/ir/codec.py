# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compatible entry points for the IR wire-format codecs."""

from archkeel.ir.codec_contract import (
    CONTRACT_SCHEMA_VERSION,
    ContractVersionError,
    absent_contract_digest,
    contract_bytes,
    contract_digest,
    parse_contract,
    parse_dependency_selector,
    parse_required_component,
)
from archkeel.ir.codec_contract import (
    _rule_payload as _rule_payload,
)
from archkeel.ir.codec_delta import (
    delta_payload,
    parse_delta,
)
from archkeel.ir.codec_governance import (
    absent_baseline_digest,
    amendment_bytes,
    baseline_bytes,
    baseline_digest,
    parse_amendment,
    parse_baseline,
    parse_lock,
    parse_measurements,
    parse_validation_baseline,
)
from archkeel.ir.codec_inside import (
    contract_provenance_paths,
    declaration_paths,
    load_inside_contract_tree,
)
from archkeel.ir.codec_observation import (
    canonical_report_bytes,
    decode_canonical_model,
    encode_canonical_model,
    observation_payload,
    parse_observation,
)
from archkeel.ir.codec_result import (
    _architecture_component_payload as _architecture_component_payload,
)
from archkeel.ir.codec_result import (
    finding_payload,
    result_bytes,
    result_payload,
)
from archkeel.ir.codec_wire import (
    canonical_json_bytes,
    decode_json,
    value_bytes,
)
from archkeel.ir.facts_codec import (
    parse_evidence,
    parse_record,
)
from archkeel.ir.model import (
    ContractInputError,
    InsideContractIssue,
    InsideContractMount,
    InsideContractTree,
    RawJson,
)

# Ordinary-module reexports need one literal declaration for proven facade routes.
__all__ = (
    "CONTRACT_SCHEMA_VERSION",
    "ContractInputError",
    "ContractVersionError",
    "InsideContractIssue",
    "InsideContractMount",
    "InsideContractTree",
    "RawJson",
    "absent_baseline_digest",
    "absent_contract_digest",
    "amendment_bytes",
    "baseline_bytes",
    "baseline_digest",
    "canonical_json_bytes",
    "canonical_report_bytes",
    "contract_bytes",
    "contract_digest",
    "contract_provenance_paths",
    "declaration_paths",
    "decode_canonical_model",
    "decode_json",
    "delta_payload",
    "encode_canonical_model",
    "finding_payload",
    "load_inside_contract_tree",
    "observation_payload",
    "parse_amendment",
    "parse_baseline",
    "parse_contract",
    "parse_dependency_selector",
    "parse_delta",
    "parse_evidence",
    "parse_lock",
    "parse_measurements",
    "parse_observation",
    "parse_record",
    "parse_required_component",
    "parse_validation_baseline",
    "result_bytes",
    "result_payload",
    "value_bytes",
)
