// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `asyncg`: a generic function polls a future once and drops it.

use std::future::Future;
use std::task::{Context, Waker};

pub fn drive<F: Future>(future: F) {
    let mut future = Box::pin(future);
    let mut context = Context::from_waker(Waker::noop());
    let _ = future.as_mut().poll(&mut context);
}
