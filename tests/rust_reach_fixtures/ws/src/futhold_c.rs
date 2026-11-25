// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `futhold`: the async block is cast to `dyn Future` at the call.

pub fn make() -> regdep::Task {
    regdep::Task::new(Box::pin(async {
        let _held = crate::futhold_b::X;
        std::future::ready(()).await;
    }))
}
