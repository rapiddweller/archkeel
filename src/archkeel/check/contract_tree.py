# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the root contract and its explicit insides once for observation and assembly (AD-34)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archkeel.ir.codec import InsideContractTree, load_inside_contract_tree
from archkeel.ir.model import ArchitectureContract, contract_relative_path

from .declarations import load_contract


@dataclass(frozen=True, slots=True)
class ContractInput:
    """The root contract, the digest of its bytes and the tree of its explicit insides."""

    contract: ArchitectureContract
    digest: str
    tree: InsideContractTree


def _read_inside(root: Path, reference: str) -> tuple[bytes, str]:
    relative = contract_relative_path(reference)
    if relative is None:
        raise ValueError("unsafe repository path")
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("file is missing or outside the repository")
    return target.read_bytes(), target.relative_to(root).as_posix()


def contract_input(
    root: Path, contract_path: Path, contract: ArchitectureContract, digest: str
) -> ContractInput:
    """Read every explicitly mounted inside contract under `root`."""
    repository = root.resolve()
    tree = load_inside_contract_tree(
        contract_path.relative_to(repository).as_posix(),
        contract,
        digest,
        contract_path.resolve().relative_to(repository).as_posix(),
        lambda reference: _read_inside(repository, reference),
    )
    return ContractInput(contract, digest, tree)


def load_contract_input(root: Path, contract_path: Path) -> ContractInput:
    contract, digest = load_contract(contract_path)
    return contract_input(root, contract_path, contract, digest)
