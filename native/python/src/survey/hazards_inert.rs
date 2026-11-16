// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bounded inert reads of imported door modules (AD-574). The import gap stays.

use std::collections::{HashMap, HashSet};

pub(super) fn modules(
    bound: &HashMap<String, Vec<String>>,
    unique: &HashSet<String>,
) -> HashMap<String, String> {
    bound
        .iter()
        .filter_map(|(name, origins)| match origins.as_slice() {
            [origin]
                if unique.contains(name)
                    && matches!(
                        origin.as_str(),
                        "pickle" | "importlib.metadata" | "importlib.abc"
                    ) =>
            {
                Some((name.clone(), origin.clone()))
            }
            _ => None,
        })
        .collect()
}

pub(super) fn read(modules: &HashMap<String, String>, name: &str, attrs: &[&str]) -> bool {
    modules.get(name).is_some_and(|module| {
        matches!(
            (module.as_str(), attrs),
            (
                "pickle",
                ["UnpicklingError" | "PickleError" | "HIGHEST_PROTOCOL"]
            ) | ("importlib.metadata", ["PackageNotFoundError"])
                | ("importlib.abc", ["Traversable"])
        )
    })
}
