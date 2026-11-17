// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! How a `from` import and a use through a module binding read a name of a package (AD-450,
//! AD-708): the submodule of that name, or an attribute of the package.

use super::{Binding, Collector};

impl Collector<'_, '_> {
    /// `from anchor import name`: the submodule `anchor.name`, whether the import gives that
    /// submodule, and whether it can give an attribute of the package as well (AD-450).
    pub(super) fn resolve(&self, anchor: &str, name: &str) -> (String, bool, bool) {
        let submodule = if anchor.is_empty() {
            name.to_owned()
        } else {
            format!("{anchor}.{name}")
        };
        let shadowed = (self.bindings.get(anchor)).is_some_and(|names| names.contains(name));
        // A submodule or a package directory: `from app import service` imports it as
        // `import app.service` does, and a directory without a module file is a gap.
        let exists = self.names.contains(submodule.as_str())
            || self.directories.contains(submodule.as_str());
        let local = !shadowed && exists;
        let open = (self.open.get(anchor)).is_some_and(|own| !own.contains(&submodule));
        let written = self.written.contains(anchor);
        let ambiguous = exists && (shadowed || open || written);
        (submodule, local, ambiguous)
    }

    /// A use of `name` through a module binding: the record of `from module import name`, with
    /// no binding (#1415, AD-708).
    pub(super) fn attribute(&mut self, found: &crate::survey::module_uses::Use) {
        let (submodule, local, ambiguous) = self.resolve(&found.module, &found.name);
        let binding = Binding {
            target: if local { &submodule } else { &found.module },
            symbol: if local { None } else { Some(&found.name) },
            binding: None,
            level: 0,
            attribute: true,
        };
        self.record((&found.range, false, found.guarded), &binding);
        let last = self.records.last().filter(|_| ambiguous);
        self.ambiguous
            .extend(last.map(|record| record.id.as_str().to_owned()));
    }
}
