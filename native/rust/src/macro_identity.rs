// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Prove that a call of a macro outside the `macro_rules!` of the workspace expands to code that
//! names no module of the crate except through the call tokens (#1371, AD-662). The scan reads
//! the tokens of such a call as code of the file; it never reads the expansion. A procedural
//! macro, or a `macro_rules!` of a crate outside the scan, can write any path, and rustc resolves
//! a `crate::` path of a `macro_rules!` body in the crate of the call. So only two kinds of macro
//! are proved, each by the same namespace proof as a derive (AD-535, L-117):
//!
//! - a macro of the standard library, by its plain name from the prelude or by a `std`, `core`
//!   or `alloc` path;
//! - a reviewed `macro_rules!` of a registry crate at a locked version, whose arms write only
//!   `$crate` and `::core` paths and the call tokens.

use crate::attrs::model::Usage;
use crate::builder::Builder;
use crate::crates::Workspace;
use crate::derive_identity::{binding, namespace};
use crate::derive_imports::Local;
use crate::modules::Index;
use crate::scan::{MacroCall, Via};
use crate::std_macros;
use crate::tree::Module;

/// A reviewed `macro_rules!` of a registry crate: package, macro, locked version.
/// - serde_json 1.0.154 `json`: `$crate::json_internal!`, which writes `$crate` paths only.
/// - schemars 1.2.3 `json_schema`: `$crate::Schema`, `::core::convert::TryFrom` and
///   `$crate::_private::serde_json::json!`.
const REGISTRY: &[(&str, &str, &str)] = &[
    ("serde_json", "json", "1.0.154"),
    ("schemars", "json_schema", "1.2.3"),
];

/// The call of the plain name `name` that a body makes at the place of `call`.
pub(crate) fn inner(call: &MacroCall, name: &str) -> MacroCall {
    MacroCall {
        name: name.to_owned(),
        path: vec![name.to_owned()],
        absolute: false,
        ..call.clone()
    }
}

impl Builder {
    /// A call whose expansion the scan does not read: a gap of its module, and the module may
    /// hold an impl that the scan does not see. A proved call is read through its tokens.
    pub(crate) fn unread_call(
        &mut self,
        (workspace, index, modules): (&Workspace, &Index<'_>, &[Module]),
        local: &Local<'_>,
        call: &MacroCall,
    ) {
        if proven(workspace, index, local, call, modules) {
            return;
        }
        let module = local.module;
        let reason = format!(
            "The macro {}! is no macro_rules! of the workspace: the scan does not read its expansion",
            call.path.join("::")
        );
        // As for an attribute macro: the gap names the source, and the target is unseen.
        let evidence = self.cite(&module.rel, &call.site);
        let source = std::iter::once(module.module.as_str())
            .chain(call.scope.iter().map(String::as_str))
            .collect::<Vec<_>>()
            .join(".");
        self.pair_gap(&reason, &evidence, (&source, ""), None);
        self.impl_home(module, call);
    }

    /// The module of the call may hold an impl that is not anchored there (AD-516).
    pub(crate) fn impl_home(&mut self, module: &Module, call: &MacroCall) {
        let home = (module.rel.clone(), call.site.clone());
        self.macro_impl_homes
            .entry(module.module.clone())
            .or_insert(home);
    }
}

/// True when the call names a macro of `STD` or `REGISTRY`, and its tokens hold no `impl`.
pub(crate) fn proven(
    workspace: &Workspace,
    index: &Index<'_>,
    local: &Local<'_>,
    call: &MacroCall,
    modules: &[Module],
) -> bool {
    let module = local.module;
    let Some(krate) = workspace.crates.get(module.crate_index) else {
        return false;
    };
    if call.writes_impl || !module.scan.extern_crates.is_empty() {
        return false;
    }
    let usage = Usage {
        path: call.path.clone(),
        absolute: call.absolute,
        complete: true,
        block: call.block,
        prelude: call.prelude,
    };
    let sysroot = |root: &str| {
        ["std", "core", "alloc"].contains(&root)
            && !module.scan.names.contains(root)
            && !krate.manifest.dependencies.contains_key(root)
    };
    match call.path.as_slice() {
        [name] if std_macros::has(name.as_str(), std_macros::PATHS_ONLY) && !call.absolute => {
            // A function or a type of the name is in another namespace: only a `use`, a
            // `macro_rules!` of the crate, an `extern crate` or a glob can bind the macro.
            let bound = (module.scan.references.iter()).any(|reference| {
                matches!(&reference.via, Via::Use { binding: Some(bound), .. } if bound == name)
            });
            let defined = modules.iter().any(|other| {
                other.crate_index == module.crate_index
                    && other.scan.macro_defs.iter().any(|def| &def.name == name)
            });
            !bound
                && !defined
                && namespace(workspace, index, local, &call.scope, &usage, name, modules)
        }
        [root, name] if std_macros::has(name.as_str(), std_macros::PATHS_ONLY) && sysroot(root) => {
            true
        }
        _ => registry(workspace, local, call, &usage),
    }
}

/// The call names a macro of `REGISTRY` through the dependency of its crate, with no glob that
/// may bind the name otherwise.
fn registry(workspace: &Workspace, local: &Local<'_>, call: &MacroCall, usage: &Usage) -> bool {
    let module = local.module;
    let Some(krate) = workspace
        .crates
        .get(module.crate_index)
        .filter(|c| !c.manifest.legacy())
    else {
        return false;
    };
    let glob = local.globs.iter().any(|r| {
        r.scope == call.scope && matches!(r.via, Via::Glob { block, .. } if !block || call.block)
    });
    if glob && !call.absolute {
        return false;
    }
    let path = if call.absolute {
        Some(call.path.clone())
    } else {
        binding(local, &call.scope, &usage.path, 0)
    };
    let Some([root, name]) = path.as_deref() else {
        return false;
    };
    let Some(package) = krate.manifest.dependencies.get(root.as_str()) else {
        return false;
    };
    if !krate.registry.direct.contains(root) || workspace.crates.iter().any(|c| &c.ident == package)
    {
        return false;
    }
    let locked = krate.registry.packages.get(package.as_str());
    REGISTRY.iter().any(|(model, macro_name, version)| {
        model == package && macro_name == name && locked.is_some_and(|l| l.version == *version)
    })
}

#[cfg(test)]
#[path = "macro_identity_tests.rs"]
mod tests;
