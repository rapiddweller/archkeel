// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `pinfut`: it polls a `Pin<Box<dyn Future>>` to its end.

use std::future::Future;
use std::task::{Context, Waker};

pub fn run() {
    let mut future = crate::pinfut_c::make();
    let mut context = Context::from_waker(Waker::noop());
    let _ = future.as_mut().poll(&mut context);
}
