# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collector ownership, package compatibility and reproducible code identity."""

from archkeel.ir.codec import parse_contract


def _contract():
    return parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
