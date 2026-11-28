// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The trojan horse form of a hazard site (AD-664).
//!
//! A trojan horse is a reference to a builtin or a function that runs a text or imports a module whose
//! name the scan does not know. Its gap stays `every_module`; the form only lets a contract name
//! the site and declare its reach. The owner admits these forms: `eval`, `exec` and `compile` of
//! a text, an unpickler, a loader with a name that the scan does not know, and `__import__`.
//! Each other hazard (a trojan horse module, a pickler, a string that names a trojan horse, the import state)
//! has no form, so no declaration can apply to it.

use archkeel_facts::data::TrojanHorseForm;
use ruff_text_size::TextRange;

use crate::survey::hazards_names::DYNAMIC;

/// A hazard or a proven import site. Trojan horse sites also carry scope and binding (AD-664).
pub(in crate::survey) struct Site {
    pub kind: &'static str,
    pub detail: String,
    pub range: TextRange,
    pub trojan_horse: Option<archkeel_facts::data::TrojanHorseForm>,
    pub scope: String,
    pub binding: Option<String>,
}

impl Site {
    /// A site of a name that carries no scope and no binding.
    pub(in crate::survey) fn plain(kind: &'static str, detail: &str, range: TextRange) -> Self {
        let (trojan_horse, scope, binding) = (None, String::new(), None);
        Self {
            kind,
            detail: detail.to_owned(),
            range,
            trojan_horse,
            scope,
            binding,
        }
    }
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

/// The calls that evaluate the string annotations of an object.
const EVALUATES: [&str; 8] = [
    "typing.get_type_hints",
    "typing._eval_type",
    "typing.evaluate_forward_ref",
    "typing_extensions.get_type_hints",
    "typing_extensions.evaluate_forward_ref",
    "inspect.signature",
    "inspect.get_annotations",
    "annotationlib.get_annotations",
];

/// The form of a site of kind `kind` with the qualified name `detail`, if it is a trojan horse whose
/// reach a contract can declare. A string literal is never a trojan horse site here: the caller does not
/// ask for it.
pub(super) fn form(kind: &str, detail: &str) -> Option<TrojanHorseForm> {
    if kind != DYNAMIC {
        return None;
    }
    let form = match detail {
        "eval" | "builtins.eval" => TrojanHorseForm::Eval,
        "exec" | "builtins.exec" => TrojanHorseForm::Exec,
        // The evaluation of an annotation runs its text as an expression (AD-1176).
        name if EVALUATES.contains(&name) => TrojanHorseForm::Eval,
        "compile" | "builtins.compile" => TrojanHorseForm::Compile,
        "__import__" | "builtins.__import__" => TrojanHorseForm::DunderImport,
        "import_module" | "importlib.import_module" => TrojanHorseForm::Loader,
        name if UNPICKLE.contains(&name) => TrojanHorseForm::Unpickle,
        _ => return None,
    };
    Some(form)
}

#[cfg(test)]
mod tests {
    use super::{form, TrojanHorseForm, DYNAMIC};
    use crate::survey::hazards::IMPORT_SYSTEM;

    #[test]
    fn each_admitted_trojan_horse_has_its_form_and_no_other_site_has_one() {
        let admitted = [
            ("eval", TrojanHorseForm::Eval),
            ("exec", TrojanHorseForm::Exec),
            ("compile", TrojanHorseForm::Compile),
            ("__import__", TrojanHorseForm::DunderImport),
            ("import_module", TrojanHorseForm::Loader),
            ("importlib.import_module", TrojanHorseForm::Loader),
            ("pickle.loads", TrojanHorseForm::Unpickle),
            ("dill.Unpickler", TrojanHorseForm::Unpickle),
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
