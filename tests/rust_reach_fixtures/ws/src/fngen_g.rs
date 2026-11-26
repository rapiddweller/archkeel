// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fngen`: a generic function coerces its closure to `Box<dyn Fn(T)>`; it has two instances.

pub fn wrap<T: 'static>(f: impl Fn(T) + 'static) -> Box<dyn Fn(T)> {
    Box::new(f)
}
