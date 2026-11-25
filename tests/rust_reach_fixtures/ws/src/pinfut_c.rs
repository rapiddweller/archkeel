// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `pinfut`: the async body holds the value across an await.

use std::future::Future;
use std::pin::Pin;

pub fn make() -> Pin<Box<dyn Future<Output = ()>>> {
    Box::pin(async {
        let _held = crate::pinfut_b::X;
        std::future::ready(()).await;
    })
}
