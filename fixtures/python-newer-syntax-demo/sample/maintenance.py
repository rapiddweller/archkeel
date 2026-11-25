# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
def purge(cell: object) -> bool:
    return cell is None


def sweep(cell: object) -> bool:
    return purge(cell)
