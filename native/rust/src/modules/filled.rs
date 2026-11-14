// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether a module may get a module name or a `use` binding from a macro call. A glob `use` of
//! such a module may bring in a name that the scan does not see.
//!
//! A plain call `m!()` names one of these: a `macro_rules!` of the crate in textual scope, a macro
//! that a `use` or a glob of the file brings in, a macro of a `#[macro_use] extern crate`, or a
//! macro of the standard prelude. A call `crate::a::m!()` names what the module `a` binds as `m`.
//! The rule reads the name only when no other binding can apply, so a match by name is a match
//! of the macro itself.

use crate::scan::{MacroCall, Reference, Via, KNOWN_MACROS};
use crate::tree::Module;

/// The file module and the lexical module that a path of modules below the crate root names.
pub(crate) type Reach<'r> = dyn Fn(&[String]) -> Option<(String, String)> + 'r;

/// Whether a call at module level of `target` may declare a module name. A call is safe only
/// when all of these hold:
///
/// 1. its tokens hold no `mod`, `use` or `extern`;
/// 2. no file of the crate has a `#[macro_use] extern crate`;
/// 3. it is a plain call, and its module has no glob `use` and no `use` that binds the name (a
///    `use` binds in its own module only); or it is `crate::a::m!()`, and the module `a` binds
///    `m` by one `use m;` only;
/// 4. exactly one `macro_rules!` of the crate has the name, and its body holds no `mod`, `use`,
///    `extern` and calls no macro; or, for a plain call, no `macro_rules!` of the crate has the
///    name and it is a macro of the standard library (`KNOWN_MACROS`).
///
/// Any other call may fill the module.
pub(crate) fn may_fill<'a>(
    target: &Module,
    reach: &Reach<'_>,
    all: impl Iterator<Item = &'a Module> + Clone,
) -> bool {
    let krate = all.filter(|module| module.crate_index == target.crate_index);
    let macro_use = krate.clone().any(|module| module.scan.macro_use_crate);
    let calls = target.scan.macro_calls.iter();
    calls.filter(|call| call.fills).any(|call| {
        let here = |r: &&Reference| r.scope == call.scope;
        let globs =
            (target.scan.references.iter().filter(here)).any(|r| matches!(r.via, Via::Glob { .. }));
        let plain = call.path.len() == 1 && !globs && !leaves(target, &call.name).any(|r| here(&r));
        let own = || own_path(call, reach, krate.clone());
        if call.declares || macro_use || !(plain || own()) {
            return true;
        }
        let mut defs = (krate.clone())
            .flat_map(|module| module.scan.macro_defs.iter())
            .filter(|def| def.name == call.name);
        match (defs.next(), defs.next()) {
            (None, _) => !(plain && KNOWN_MACROS.contains(&call.name.as_str())),
            (Some(def), None) => def.declares || !def.calls.is_empty(),
            (Some(_), Some(_)) => true,
        }
    })
}

/// The `use` leaves of `module` that bind `name`.
fn leaves<'m>(module: &'m Module, name: &'m str) -> impl Iterator<Item = &'m Reference> {
    let binds =
        move |r: &&Reference| matches!(&r.via, Via::Use { binding: Some(b), .. } if b == name);
    module.scan.references.iter().filter(binds)
}

/// Whether the call is `crate::a::m!()`, and the module `a` binds `m` by one `use m;` only. That
/// `use` names the one `macro_rules!` of its name, and an explicit `use` hides a glob.
fn own_path<'a>(
    call: &MacroCall,
    reach: &Reach<'_>,
    mut krate: impl Iterator<Item = &'a Module>,
) -> bool {
    let [first, middle @ .., name] = call.path.as_slice() else {
        return false;
    };
    let Some((file, lexical)) = (first == "crate" && !middle.is_empty())
        .then(|| reach(middle))
        .flatten()
    else {
        return false;
    };
    let Some(module) = krate.find(|module| module.module == file) else {
        return false;
    };
    let found: Vec<&Reference> = leaves(module, name).collect();
    let at = |leaf: &Reference| {
        (leaf.scope.iter()).fold(module.module.clone(), |id, part| format!("{id}.{part}"))
    };
    matches!(found.as_slice(), [leaf] if leaf.names == [name.clone()] && at(leaf) == lexical)
}
