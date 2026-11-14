// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `super` steps of a path: which module each one climbs to.

/// Climb one module for each `super` that starts `names` at `at`: the module, the number of
/// steps and the index after the last `super`. `Err` says why a step leaves the crate.
pub(crate) fn ascend(
    root: &str,
    from: &str,
    names: &[String],
    mut at: usize,
) -> Result<(String, i64, usize), &'static str> {
    let (mut cur, mut ups) = (from.to_owned(), 0);
    while names.get(at).map(String::as_str) == Some("super") {
        if cur == root {
            return Err("super names a module above the crate root");
        }
        cur = cur
            .rsplit_once('.')
            .map_or(cur.clone(), |(parent, _)| parent.to_owned());
        ups += 1;
        at += 1;
    }
    Ok((cur, ups, at))
}

/// Whether `module` is `root` or a module below it.
pub(crate) fn inside(module: &str, root: &str) -> bool {
    module == root
        || module
            .strip_prefix(root)
            .is_some_and(|rest| rest.starts_with('.'))
}
