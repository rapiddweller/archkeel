// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The standard library of each profile, pinned in the build (AD-388, #1073 item 5).
//!
//! The shell sends the standard library of the profile of a reply, and an import of such a name is
//! no external dependency. A caller must not widen it by word: a name that is not in the pinned
//! list of the profile refuses the settings (`Settings::check` of the model). A shorter list only
//! makes the core stricter. The list of `archkeel-python-analyzer` is `sys.stdlib_module_names`
//! of CPython 3.11 to 3.14, one list for each minor (`archkeel-python-analyzer@3.11`). CPython
//! defines that set to be the same on each platform, so a name is accepted when it is in the
//! list of any supported minor. `sys.builtin_module_names` depends on the build and is not used
//! (`tests/test_native_standard_library.py` checks the list of the running interpreter).
//!
//! The table is a data file, one `owner name` pair on each line, in sorted order. The owner is
//! the profile, or the profile and a minor version after `@`.

use archkeel_facts::envelope::Profile;

const TABLE: &str = include_str!("standard_library.txt");

/// The pinned standard library of a profile: the names of each of its versions, in sorted order
/// and without a duplicate.
pub fn standard_library(profile: Profile) -> Vec<&'static str> {
    let mut names: Vec<&'static str> = TABLE
        .lines()
        .filter_map(|line| line.split_once(' '))
        .filter(|(owner, _)| owner.split('@').next() == Some(profile.as_str()))
        .map(|(_, name)| name)
        .collect();
    names.sort_unstable();
    names.dedup();
    names
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_list_is_sorted_and_has_no_duplicate() {
        let lines: Vec<&str> = TABLE.lines().collect();
        assert!(lines.windows(2).all(|pair| pair[0] < pair[1]));
        assert!(lines.iter().all(|line| line.split(' ').count() == 2));
        for profile in Profile::ALL.iter().copied() {
            let names = standard_library(profile);
            assert!(
                names.windows(2).all(|pair| pair[0] < pair[1]),
                "{profile:?}"
            );
        }
        assert!(standard_library(Profile::Python).contains(&"os"));
        assert!(!standard_library(Profile::Python).contains(&"requests"));
        // A name of the build, not of the standard library, is outside the list.
        assert!(!standard_library(Profile::Python).contains(&"xxsubtype"));
        assert!(standard_library(Profile::TypeScript).is_empty());
        assert_eq!(standard_library(Profile::Dart).len(), 1);
        assert_eq!(standard_library(Profile::Rust).len(), 3);
    }
}
