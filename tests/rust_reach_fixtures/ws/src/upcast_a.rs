// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `upcast`: it holds a `dyn Tr` that came from a `dyn Sub` and never names the `dyn Sub`.

pub fn run() {
    crate::upcast_u::get().hit();
}
