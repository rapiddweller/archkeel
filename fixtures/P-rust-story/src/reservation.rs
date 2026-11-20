// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use crate::stock::available as check_stock;

pub(super) fn request(available: u32) -> bool {
    self::can_reserve(available)
}

fn can_reserve(available: u32) -> bool {
    check_stock(available)
}
