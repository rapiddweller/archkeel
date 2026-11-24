// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `arcfn`: a closure that holds the value goes into a container of `std`.

use std::collections::HashMap;
use std::sync::Arc;

pub fn make() -> HashMap<u8, Arc<dyn Fn() + Send + Sync>> {
    let held = crate::arcfn_b::X;
    let mut map: HashMap<u8, Arc<dyn Fn() + Send + Sync>> = HashMap::new();
    map.insert(1, Arc::new(move || {
        let _ = &held;
    }));
    map
}
