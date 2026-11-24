// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `mpsc`.

use std::sync::mpsc::{channel, Receiver, Sender};

pub fn pair() -> (Sender<Box<dyn Send>>, Receiver<Box<dyn Send>>) {
    let (sender, receiver) = channel::<Box<dyn Send>>();
    sender.send(Box::new(crate::mpsc_b::X)).unwrap();
    (sender, receiver)
}
