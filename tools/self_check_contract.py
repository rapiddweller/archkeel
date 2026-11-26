# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Normalize the root contract without dropping any verdict input."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def normalize_contract(result: dict[str, Any], root: Path, revision: str = "") -> None:
    """Bind every inside contract, or conservatively bind every input if one is unavailable."""
    scope, inputs = result.get("scope"), result.get("contract_files")
    if (
        not isinstance(scope, dict)
        or not isinstance(inputs, dict)
        or result.get("contract_normalized")
    ):
        return
    digest = scope.get("contract")
    paths = [path for path, value in inputs.items() if value == digest and isinstance(path, str)]
    if not isinstance(digest, str):
        return
    fallback = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    try:
        if not paths:
            raise ValueError("root contract is unavailable")
        pending = [paths[0]]
        contracts: dict[str, Any] = {}
        while pending:
            path = pending.pop()
            if path in contracts:
                continue
            if revision:
                done = subprocess.run(
                    ["git", "show", f"{revision}:{path}"], cwd=root, capture_output=True, check=True
                )
                data = done.stdout
            else:
                data = (root / path).read_bytes()
            if hashlib.sha256(data).hexdigest() != inputs.get(path):
                raise ValueError("contract input differs from its recorded digest")
            contract = json.loads(data)
            if not isinstance(contract, dict) or not isinstance(contract.get("components"), list):
                raise ValueError("contract has no component list")
            for component in contract["components"]:
                if not isinstance(component, dict):
                    raise ValueError("component is not an object")
                if "inside" in component:
                    pending.append(component["inside"])
            contract["components"].sort(key=lambda row: json.dumps(row, sort_keys=True))
            contracts[path] = contract
        canonical = json.dumps(contracts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        data = canonical.encode("utf-8")
    except (OSError, ValueError, TypeError, subprocess.CalledProcessError):
        data = fallback
    scope["contract"] = hashlib.sha256(data).hexdigest()
    result["contract_normalized"] = True
