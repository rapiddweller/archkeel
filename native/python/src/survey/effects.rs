// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the gap of each import site leaves unknown (AD-564).
//!
//! The model holds with a gap only the rules that read its effect, so each statement here must
//! name all that the site can change. A kind without a statement leaves the whole scope unknown.
//!
//! - A dynamic import or a change of the import system can run code that the scan cannot see.
//!   Such code can replace a module in `sys.modules`, so an import of any module can give
//!   another module than the one that it names: the code of every module is unknown. This
//!   holds for a loader call with an unknown name too: `import_module(name)` can return `sys`
//!   or `builtins`, and no later site names a write through that value.
//! - A star import of a project module binds names that the scan does not know, and it imports
//!   each submodule that `__all__` of the package names: the code of the source module is
//!   unknown.
//! - A name that can be an attribute or a submodule leaves the target of the import and the
//!   binding of the source module unknown: the code of the source module is unknown.
//! - A relative import above the top package, or an import of a project module that the scan
//!   does not find, fails or loads a file that the scan cannot see: that is unseen code too.
//! - A module whose top package lies above its scan root is read, but its place in the layout
//!   is not proven (`layout.rs`): its file and layout are unknown, its code is known.
//!
//! `UNSEEN_CODE` is the one switch for a site that can run unseen code.

use archkeel_facts::data::GapEffect;
use archkeel_facts::ids::ModuleName;

use super::hazards;

/// The named gaps of the import sites (`targets.rs`).
pub(super) const BEYOND_TOP: &str = "relative_import_beyond_top";
pub(super) const NOT_FOUND: &str = "project_module_not_found";
pub(super) const STAR: &str = "star_import";
pub(super) const AMBIGUOUS: &str = "reexport_ambiguity";

/// The effect of a site that can run code that the scan cannot see.
const UNSEEN_CODE: GapEffect = GapEffect::EveryModule;

/// The effect of the gap of kind `kind` at a site of `module`, if the collector can state one.
pub(super) fn of(kind: &str, module: &str) -> Option<GapEffect> {
    match kind {
        hazards::DYNAMIC | hazards::IMPORT_SYSTEM | BEYOND_TOP | NOT_FOUND => Some(UNSEEN_CODE),
        STAR | AMBIGUOUS => Some(GapEffect::Modules {
            modules: vec![ModuleName::new(module)],
        }),
        _ => None,
    }
}

/// The effect of the layout gap of `module`: its file and its place in the layout.
pub(super) fn layout(module: &str) -> GapEffect {
    GapEffect::Layout {
        modules: vec![ModuleName::new(module)],
    }
}

#[cfg(test)]
#[path = "effects_tests.rs"]
mod tests;
