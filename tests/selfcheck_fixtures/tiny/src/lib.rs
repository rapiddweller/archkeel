// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

mod reservation;
mod stock;

pub fn reserve(available: u32) -> bool {
    reservation::request(available)
}

fn has_stock(available: u32) -> bool {
    available > 0
}
