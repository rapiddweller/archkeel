// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A project module that binds a standard library module hands it to another module (AD-1094,
//! #1973). `util.py` holds `import cProfile`, and `app.util.cProfile.run(text)` runs the text.

use std::collections::HashMap;

use crate::survey::hazards_names::first_hazard;
use crate::survey::hazards_names::holds;

/// The names that the modules of the scan bind to a module that holds a hazard name (`import dis`,
/// `from unittest import mock`), with their qualified origins.
pub(in crate::survey) type Reexports = HashMap<String, Vec<String>>;

/// The re-exported names of all modules, from the import bindings of each module.
pub(in crate::survey) fn table<'a>(
    modules: impl Iterator<Item = &'a HashMap<String, Vec<String>>>,
) -> Reexports {
    let mut found = Reexports::new();
    for bound in modules {
        for (name, origins) in bound {
            let held = origins.iter().filter(|origin| holds(origin));
            found.entry(name.clone()).or_default().extend(held.cloned());
        }
    }
    found.retain(|_, origins| !origins.is_empty());
    found
}

/// The first hazard on `attributes` when one attribute is a re-exported name: the rest of the
/// chain is read from the origin of that name.
pub(super) fn find(reexports: &Reexports, attributes: &[&str]) -> Option<(&'static str, String)> {
    attributes.iter().enumerate().find_map(|(at, name)| {
        let origins = reexports.get(*name)?;
        origins
            .iter()
            .find_map(|origin| first_hazard(origin.clone(), &attributes[at + 1..]))
    })
}

/// The first hazard on `attributes` read from a name that `origin` gives: a project module that
/// binds a re-exported name (`from app.util import cp`, origin `app.util.cp`).
pub(super) fn find_from(
    reexports: &Reexports,
    origin: &str,
    attributes: &[&str],
) -> Option<(&'static str, String)> {
    let mut parts: Vec<&str> = origin.split('.').collect();
    parts.extend(attributes);
    find(reexports, &parts)
}

/// True when `origin` is a module with a hazard name, or a name that a module of the scan binds to
/// one (`app.util.cp`): the origin is such a module as a value.
pub(super) fn value(reexports: &Reexports, origin: &str) -> bool {
    let named = origin
        .rsplit_once('.')
        .is_some_and(|(_, last)| reexports.contains_key(last));
    holds(origin) || named
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
        let table = table(all.iter());
        assert_eq!(
            find(&table, &["cProfile", "run"]).map(|x| x.1).as_deref(),
            Some("cProfile.run")
        );
        assert_eq!(
            find(&table, &["mock", "patch"]).map(|x| x.1).as_deref(),
            Some("unittest.mock.patch")
        );
        assert_eq!(find(&table, &["os", "path"]), None);
        assert_eq!(find(&table, &["cProfile", "Stats"]), None);
        assert_eq!(find(&table, &["run"]), None);
    }

    #[test]
    fn a_from_import_of_a_re_exported_name_reads_the_chain_and_the_value() {
        let all = [bound(&[("cp", "cProfile")])];
        let table = table(all.iter());
        let found = find_from(&table, "app.util.cp", &["run"]).map(|x| x.1);
        assert_eq!(found.as_deref(), Some("cProfile.run"));
        assert!(value(&table, "app.util.cp"));
        assert!(!value(&table, "app.util.other"));
        assert!(!value(&table, "cp"));
        assert!(value(&table, "unittest"));
    }
}
