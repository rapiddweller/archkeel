# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-30: the repeated-logic claim needs a signal and a declared owner to contradict."""

from fixtures.architecture_demo import CATALOG

_TOUR = next(variant for variant in CATALOG if variant.id == "tour")
