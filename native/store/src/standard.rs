// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The pinned standard library and SDK libraries, read by the owner key that a reply names
//! (AD-388, #1073 item 5, AD-688).
//!
//! The shell sends the standard library of a reply, and an import of such a name is no external
//! dependency. A caller must not widen it by word: a name that is not in the pinned list of the
//! family of the key refuses the settings (`Settings::check` of the model). A shorter list only
//! makes the core stricter. The Python lists are `sys.stdlib_module_names` of CPython 3.11 to
//! 3.14, one list for each minor (`archkeel-python-analyzer@3.11`). CPython defines that set to be
//! the same on each platform, so a name is accepted when it is in the list of any supported minor
//! of the family. `sys.builtin_module_names` depends on the build and is not used
//! (`tests/test_native_standard_library.py` checks the list of the running interpreter).
//!
//! The tables are data files of `archkeel-facts`, one `owner name` pair on each line, in sorted
//! order. The owner is a family (the profile), or a family and a minor version after `@`. A reply
//! names its key in its validation block; the store reads no language here.

use archkeel_facts::envelope::validation::library_family;

const TABLE: &str = archkeel_facts::STANDARD_LIBRARY;

/// The `owner name` rows of a table.
fn rows(table: &'static str) -> impl Iterator<Item = (&'static str, &'static str)> {
    table.lines().filter_map(|line| line.split_once(' '))
}

/// The SDK libraries that a contract can forbid by name although no scan lists them as a module
/// (`dart.io`): the pinned rows of the family of `key`. A family without such libraries has none,
/// and a name that is not in the list is not exempt.
pub fn sdk_libraries(key: &str) -> Vec<&'static str> {
    let family = library_family(key);
    rows(archkeel_facts::SDK_LIBRARIES)
        .filter_map(|(owner, name)| (owner == family).then_some(name))
        .collect()
}

/// The pinned standard library of the family of `key`: the names of each of its versions, in
/// sorted order and without a duplicate.
pub fn standard_library(key: &str) -> Vec<&'static str> {
    let family = library_family(key);
    let mut names: Vec<&'static str> = rows(TABLE)
        .filter(|(owner, _)| library_family(owner) == family)
        .map(|(_, name)| name)
        .collect();
    names.sort_unstable();
    names.dedup();
    names
}

/// The names that are standard in each version list of the family of `key`, in sorted order
/// (AD-450). A name that only some versions have is not in this list, so the core never takes it
/// for a standard module of a project whose version it does not know. A family without versions
/// has one list, and this is that list.
pub fn standard_library_everywhere(key: &str) -> Vec<&'static str> {
    let family = library_family(key);
    let mut owners: Vec<&'static str> = Vec::new();
    let mut found: Vec<(&'static str, &'static str)> = Vec::new();
    for (owner, name) in rows(TABLE).filter(|(owner, _)| library_family(owner) == family) {
        if !owners.contains(&owner) {
            owners.push(owner);
        }
        found.push((owner, name));
    }
    standard_library(key)
        .into_iter()
        .filter(|name| {
            owners
                .iter()
                .all(|owner| found.iter().any(|row| row == &(*owner, *name)))
        })
        .collect()
}

/// The pinned names of the key of a reply, or none when the table of a versioned key
/// (`family@minor`) is unavailable. A key without a version has the list of its whole family.
pub fn standard_library_at(key: &str) -> Option<Vec<&'static str>> {
    if !key.contains('@') {
        return Some(standard_library_everywhere(key));
    }
    let names: Vec<_> = rows(TABLE)
        .filter_map(|(owner, name)| (owner == key).then_some(name))
        .collect();
    (!names.is_empty()).then_some(names)
}

#[cfg(test)]
mod tests {
    use super::*;

    const PYTHON: &str = "archkeel-python-analyzer";
    const FAMILIES: [&str; 4] = [
        PYTHON,
        "archkeel-dart-analyzer",
        "archkeel-typescript-imports",
        "archkeel-rust-imports",
    ];

    #[test]
    fn each_list_is_sorted_and_has_no_duplicate() {
        for table in [TABLE, archkeel_facts::SDK_LIBRARIES] {
            let lines: Vec<&str> = table.lines().collect();
            assert!(lines.windows(2).all(|pair| pair[0] < pair[1]));
            assert!(lines.iter().all(|line| line.split(' ').count() == 2));
        }
        for family in FAMILIES {
            let names = standard_library(family);
            assert!(names.windows(2).all(|pair| pair[0] < pair[1]), "{family}");
        }
        assert!(standard_library(PYTHON).contains(&"os"));
        assert!(!standard_library(PYTHON).contains(&"requests"));
        // A name of the build, not of the standard library, is outside the list.
        assert!(!standard_library(PYTHON).contains(&"xxsubtype"));
        assert!(standard_library("archkeel-typescript-imports").is_empty());
        assert_eq!(standard_library("archkeel-dart-analyzer").len(), 1);
        // A versioned key reads the whole family.
        assert_eq!(
            standard_library("archkeel-python-analyzer@3.12"),
            standard_library(PYTHON)
        );
    }

    #[test]
    fn a_name_of_only_some_versions_is_not_standard_everywhere() {
        let everywhere = standard_library_everywhere(PYTHON);
        assert!(everywhere.contains(&"os"));
        // `distutils` left the standard library in 3.12; `_interpreters` arrived in 3.13.
        assert!(standard_library(PYTHON).contains(&"distutils"));
        assert!(!everywhere.contains(&"distutils"));
        assert!(!everywhere.contains(&"_interpreters"));
        for family in &FAMILIES[1..] {
            assert_eq!(
                standard_library_everywhere(family),
                standard_library(family)
            );
        }
        assert_eq!(standard_library("archkeel-rust-imports").len(), 3);
    }

    #[test]
    fn each_versioned_key_uses_only_its_own_table() {
        let at = |minor: &str| standard_library_at(&format!("{PYTHON}@3.{minor}"));
        let (at_311, at_312, at_313) = (at("11").unwrap(), at("12").unwrap(), at("13").unwrap());
        assert!(at_311.contains(&"distutils"));
        assert!(!at_312.contains(&"distutils"));
        assert!(!at_312.contains(&"_interpreters"));
        assert!(at_313.contains(&"_interpreters"));
        assert!(at("10").is_none());
        assert_eq!(
            standard_library_at("archkeel-rust-imports").unwrap().len(),
            3
        );
        assert_eq!(
            standard_library_at("archkeel-typescript-imports"),
            Some(Vec::new())
        );
    }

    #[test]
    fn the_sdk_libraries_are_the_pinned_rows_of_the_family() {
        let dart = sdk_libraries("archkeel-dart-analyzer");
        assert_eq!(dart.len(), 22);
        assert!(dart.contains(&"dart.io"));
        for family in [
            PYTHON,
            "archkeel-typescript-imports",
            "archkeel-rust-imports",
        ] {
            assert!(sdk_libraries(family).is_empty());
        }
    }
}
