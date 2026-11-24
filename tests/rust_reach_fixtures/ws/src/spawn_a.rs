// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `spawn`: a thread drops a value that it got as `Box<dyn Send>`.

pub fn run() {
    let value = crate::spawn_c::make();
    std::thread::spawn(move || drop(value)).join().unwrap();
}
