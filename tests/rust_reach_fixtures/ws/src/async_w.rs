// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The async function of the case `async`: its future holds the type across an await.

pub async fn work() {
    let _held = crate::async_b::D;
    std::future::pending::<()>().await;
}
