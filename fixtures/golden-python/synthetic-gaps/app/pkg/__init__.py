# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
try:
    from app.pkg.fast import helper
except ImportError:
    from app.pkg.slow import helper
