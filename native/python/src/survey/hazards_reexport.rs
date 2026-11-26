// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A project module that binds a standard library module hands it to another module (AD-1094,
//! #1973). `util.py` holds `import cProfile`, and `app.util.cProfile.run(text)` runs the text.

use std::collections::{HashMap, HashSet};

use crate::survey::hazards_names::first_hazard;
use crate::survey::hazards_names::holds;

/// The names that the modules of the scan bind to a module that holds a hazard name (`import dis`,
/// `from unittest import mock`), with their qualified origins, and the top packages of the scan.
#[derive(Default)]
pub(in crate::survey) struct Reexports {
    names: HashMap<String, Vec<String>>,
    packages: HashSet<String>,
}

impl Reexports {
    pub(in crate::survey) fn new() -> Self {
        Self::default()
    }

    /// True when `origin` is a module of the scan: only such a module hands on a re-exported name.
    pub(super) fn project(&self, origin: &str) -> bool {
        origin
            .split('.')
            .next()
            .is_some_and(|top| self.packages.contains(top))
    }
}

/// The re-exported names of all modules, from the import bindings of each module.
pub(in crate::survey) fn table<'a>(
    modules: impl Iterator<Item = (&'a str, &'a HashMap<String, Vec<String>>)>,
) -> Reexports {
    let mut found = Reexports::new();
    for (module, bound) in modules {
        found
            .packages
            .extend(module.split('.').next().map(str::to_owned));
        for (name, origins) in bound {
            let held = origins.iter().filter(|origin| holds(origin));
            found
                .names
                .entry(name.clone())
                .or_default()
                .extend(held.cloned());
        }
    }
    found.names.retain(|_, origins| !origins.is_empty());
    found
}

/// The first hazard on `attributes` when one attribute is a re-exported name: the rest of the
/// chain is read from the origin of that name. `via` holds the import origins of the base name: an
/// import of a module outside the scan (`pa.types`) hands on no name of the scan (AD-1133).
pub(super) fn find(
    reexports: &Reexports,
    via: Option<&Vec<String>>,
    attributes: &[&str],
) -> Option<(&'static str, String)> {
    if via.is_some_and(|all| !all.iter().any(|origin| reexports.project(origin))) {
        return None;
    }
    attributes.iter().enumerate().find_map(|(at, name)| {
        let origins = reexports.names.get(*name)?;
        origins
            .iter()
            .find_map(|origin| first_hazard(origin.clone(), &attributes[at + 1..]))
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bound(pairs: &[(&str, &str)]) -> HashMap<String, Vec<String>> {
        let owned = |(name, origin): &(&str, &str)| (name.to_string(), vec![origin.to_string()]);
        pairs.iter().map(owned).collect()
    }

    #[test]
    fn a_name_bound_to_a_module_that_holds_a_hazard_is_re_exported() {
        let all = [bound(&[
            ("cProfile", "cProfile"),
            ("mock", "unittest.mock"),
            ("os", "os"),
        ])];
        let table = table(all.iter().map(|each| ("app.util", each)));
        assert_eq!(
            find(&table, None, &["cProfile", "run"])
                .map(|x| x.1)
                .as_deref(),
            Some("cProfile.run")
        );
        assert_eq!(
            find(&table, None, &["mock", "patch"])
                .map(|x| x.1)
                .as_deref(),
            Some("unittest.mock.patch")
        );
        assert_eq!(find(&table, None, &["os", "path"]), None);
        assert_eq!(find(&table, None, &["cProfile", "Stats"]), None);
        assert_eq!(find(&table, None, &["run"]), None);
    }
}
