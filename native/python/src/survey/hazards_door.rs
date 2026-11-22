// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The door form of a hazard site (AD-664).
//!
//! A door is a reference to a builtin or a function that runs a text or imports a module whose
//! name the scan does not know. Its gap stays `every_module`; the form only lets a contract name
//! the site and declare its reach. The owner admits these forms: `eval`, `exec` and `compile` of
//! a text, an unpickler, a loader with a name that the scan does not know, and `__import__`.
//! Each other hazard (a door module, a pickler, a string that names a door, the import state)
//! has no form, so no declaration can apply to it.

use archkeel_facts::data::DoorForm;
use ruff_text_size::TextRange;

use crate::survey::hazards_names::DYNAMIC;

/// A hazard or a proven import site. Door sites also carry scope and binding (AD-664).
pub(in crate::survey) struct Site {
    pub kind: &'static str,
    pub detail: String,
    pub range: TextRange,
    pub door: Option<archkeel_facts::data::DoorForm>,
    pub scope: String,
    pub binding: Option<String>,
}

/// The functions of an unpickler: each imports the module that its bytes name.
const UNPICKLE: [&str; 11] = [
    "pickle.load",
    "pickle.loads",
    "pickle.Unpickler",
    "_pickle.load",
    "_pickle.loads",
    "_pickle.Unpickler",
    "dill.load",
    "dill.loads",
    "dill.Unpickler",
    "cloudpickle.load",
    "cloudpickle.loads",
];

/// The form of a site of kind `kind` with the qualified name `detail`, if it is a door whose
/// reach a contract can declare. A string literal is never a door site here: the caller does not
/// ask for it.
pub(super) fn form(kind: &str, detail: &str) -> Option<DoorForm> {
    if kind != DYNAMIC {
        return None;
    }
    let form = match detail {
        "eval" | "builtins.eval" => DoorForm::Eval,
        "exec" | "builtins.exec" => DoorForm::Exec,
        "compile" | "builtins.compile" => DoorForm::Compile,
        "__import__" | "builtins.__import__" => DoorForm::DunderImport,
        "import_module" | "importlib.import_module" => DoorForm::Loader,
        name if UNPICKLE.contains(&name) => DoorForm::Unpickle,
        _ => return None,
    };
    Some(form)
}

#[cfg(test)]
mod tests {
    use super::{form, DoorForm, DYNAMIC};
    use crate::survey::hazards::IMPORT_SYSTEM;

    #[test]
    fn each_admitted_door_has_its_form_and_no_other_site_has_one() {
        let admitted = [
            ("eval", DoorForm::Eval),
            ("exec", DoorForm::Exec),
            ("compile", DoorForm::Compile),
            ("__import__", DoorForm::DunderImport),
            ("import_module", DoorForm::Loader),
            ("importlib.import_module", DoorForm::Loader),
            ("pickle.loads", DoorForm::Unpickle),
            ("dill.Unpickler", DoorForm::Unpickle),
        ];
        for (detail, expected) in admitted {
            assert_eq!(form(DYNAMIC, detail), Some(expected), "{detail}");
        }
        let refused = [
            "pickle",
            "pickle.dumps",
            "pickle.Pickler",
            "dill",
            "importlib",
            "__builtins__",
            "globals",
            "code",
            "pkgutil.walk_packages",
            "types.FunctionType",
        ];
        for detail in refused {
            assert_eq!(form(DYNAMIC, detail), None, "{detail}");
        }
        assert_eq!(form(IMPORT_SYSTEM, "eval"), None);
    }
}
