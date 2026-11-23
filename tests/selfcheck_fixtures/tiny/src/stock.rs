// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

pub(crate) fn available(count: u32) -> bool {
    let present = super::has_stock(count);
    debug_assert_eq!(present, count > 0);
    present
}
