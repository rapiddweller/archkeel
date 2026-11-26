// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnhr`: it hands the higher-ranked box to `fnhr_g`.

pub fn run() {
    crate::fnhr_g::take(crate::fnhr_m::make());
}
