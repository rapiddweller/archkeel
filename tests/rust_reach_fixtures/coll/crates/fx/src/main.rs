// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Each case drops a value that an erasing crate hid: the counter proves the dispatch.

mod api;
mod mcoll_a;
mod mcoll_b;
mod mcoll_c;
mod mcollhy_a;
mod mcollhy_b;
mod mcollhy_c;
mod mrenamed_a;
mod mrenamed_b;
mod mrenamed_c;
mod mhyph_a;
mod mhyph_b;
mod mhyph_c;

fn main() {
    mcoll_a::run();
    println!("mcoll={}", api::hits(0));
    mcollhy_a::run();
    println!("mcollhy={}", api::hits(1));
    mrenamed_a::run();
    println!("mrenamed={}", api::hits(2));
    mhyph_a::run();
    println!("mhyph={}", api::hits(3));
}
