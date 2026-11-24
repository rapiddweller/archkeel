// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The case `ctl`: it formats a `Box<dyn Debug>`.

pub fn run() -> usize {
    format!("{:?}", crate::ctl_c::make()).len()
}
