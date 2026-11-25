// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `mcollhy`: it drops a value that the vendored crate `m_hy` erased, next to the member `m-hy`.

pub fn run() {
    drop(crate::mcollhy_c::make());
}
