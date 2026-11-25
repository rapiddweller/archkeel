// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `jobup`: the async block is a `dyn Job` here; the upcast to `dyn Future` is in the dependency.

pub fn make() -> std::pin::Pin<Box<dyn std::future::Future<Output = ()>>> {
    regdep::up_job(Box::pin(async {
        let _held = crate::jobup_b::X;
        std::future::ready(()).await;
    }))
}
