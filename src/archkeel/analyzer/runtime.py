# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The installed shell version that bundled collectors must report."""

import importlib.metadata


def package_version() -> str:
    """The installed Archkeel version; a checkout without metadata gives `0+unknown`."""
    try:
        return importlib.metadata.version("archkeel")
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"
