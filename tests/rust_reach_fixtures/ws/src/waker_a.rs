// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `waker`: it drops a `Waker` whose data pointer holds a value of `b`.

pub fn run() {
    drop(crate::waker_c::make());
}
