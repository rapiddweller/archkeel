// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The caller of the case `asyncg`: it hands an async block to the generic function.

pub async fn work() {
    let _held = crate::asyncg_b::D;
    std::future::pending::<()>().await;
}

pub fn run() {
    crate::asyncg_a::drive(work());
}
