// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module name of a Dart source, as `ir.facts.dart_module_name` spells it.

/// The dotted name of `path`, relative to its source root: `.dart` is removed from the last
/// segment, and `.` and `-` become `_`. `None` when a segment is not an identifier. Two paths can
/// give one name (`a-b.dart`, `a_b.dart`); the collision is a problem of the discovery.
pub(crate) fn dart_module_name(path: &str) -> Option<String> {
    let segments: Vec<&str> = path.split('/').collect();
    let last = segments.len() - 1;
    let names: Vec<String> = segments
        .iter()
        .enumerate()
        .map(|(index, segment)| {
            let segment = if index == last {
                segment.strip_suffix(".dart").unwrap_or(segment)
            } else {
                segment
            };
            segment.replace(['.', '-'], "_")
        })
        .collect();
    names
        .iter()
        .all(|name| is_identifier(name))
        .then(|| names.join("."))
}

/// `[A-Za-z_][A-Za-z0-9_]*`: a module segment and a package name.
pub(crate) fn is_identifier(name: &str) -> bool {
    let mut chars = name.chars();
    chars
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

#[cfg(test)]
mod tests {
    use super::dart_module_name;

    // The expected values come from `ir.facts.dart_module_name`.
    #[test]
    fn a_path_gives_the_python_module_name() {
        let name = |path| dart_module_name(path);
        assert_eq!(name("lib/src/a.dart").as_deref(), Some("lib.src.a"));
        assert_eq!(name("lib/a-b.g.dart").as_deref(), Some("lib.a_b_g"));
        assert_eq!(name("my-pkg/a.dart").as_deref(), Some("my_pkg.a"));
        assert_eq!(name("lib/9a.dart"), None);
        assert_eq!(name(".dart"), None);
        assert_eq!(name("lib/é.dart"), None);
        assert_eq!(name("_x/.hidden.dart").as_deref(), Some("_x._hidden"));
    }
}
