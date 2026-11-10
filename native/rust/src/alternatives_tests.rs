// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the module walk. Each fixture is the text of one file.

use std::collections::BTreeSet;

use super::*;
use crate::scan::scan;

fn reasons(text: &str) -> Vec<String> {
    let mut found = scan(text, &BTreeSet::new(), false).unwrap();
    release(&mut found);
    found.concerns.into_iter().map(|c| c.reason).collect()
}

#[test]
fn cfg_alternatives_of_one_module_name_give_no_gap() {
    let both = "#[cfg(unix)]\nmod m;\n#[cfg(not(unix))]\nmod m;\n";
    assert_eq!(reasons(both), Vec::<String>::new());
}

#[test]
fn a_cfg_module_with_no_cfg_alternative_stays_a_gap() {
    assert_eq!(reasons("#[cfg(unix)]\nmod m;\nmod m;\n").len(), 1);
    assert_eq!(
        reasons("#[cfg(unix)]\nmod m;\n#[cfg(unix)]\nmod n;\n").len(),
        2
    );
}
