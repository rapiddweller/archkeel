// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `mpsc`: the receiver drops a value that a channel carried.

pub fn run() {
    let (sender, receiver) = crate::mpsc_c::pair();
    drop(sender);
    drop(receiver.recv());
}
