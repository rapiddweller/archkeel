// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `jobup`: it runs a future that a dependency upcast from a `dyn Job`.

use std::future::Future;
use std::task::{Context, Waker};

pub fn run() {
    let mut future = crate::jobup_c::make();
    let mut context = Context::from_waker(Waker::noop());
    let _ = future.as_mut().poll(&mut context);
}
