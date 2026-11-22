// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that are trojan horses or state of the import system (AD-450, AD-472).

/// The named gaps of the sites.
pub(in crate::survey) const DYNAMIC: &str = "dynamic_import";
pub(in crate::survey) const IMPORT_SYSTEM: &str = "import_system_change";

/// The inert literal import names (AD-472).
const INERT: [&str; 2] = [
    "importlib.metadata.version",
    "importlib.metadata.PackageNotFoundError",
];

/// The gap of a qualified name: a trojan horse, the import state, or a name below one of them.
pub(in crate::survey) fn hazard(name: &str) -> Option<&'static str> {
    if INERT.contains(&name) {
        return None;
    }
    let under = |entry: &&str| {
        name == *entry
            || name
                .strip_prefix(*entry)
                .is_some_and(|rest| rest.starts_with('.'))
    };
    if STATE.iter().any(under) {
        Some(IMPORT_SYSTEM)
    } else if trojan_horses().any(|trojan_horse| under(&trojan_horse)) {
        Some(DYNAMIC)
    } else {
        None
    }
}

/// True for a module above a hazard name.
pub(super) fn above(name: &str) -> bool {
    let prefix = format!("{name}.");
    trojan_horses()
        .chain(STATE)
        .any(|entry| entry.starts_with(&prefix))
}

/// The first hazard on a qualified attribute chain.
pub(super) fn first_hazard(origin: String, attributes: &[&str]) -> Option<(&'static str, String)> {
    let mut name = origin;
    for attribute in attributes {
        name = format!("{name}.{attribute}");
        if let Some(kind) = hazard(&name) {
            return Some((kind, name));
        }
    }
    above(&name).then_some((DYNAMIC, name))
}
/// The trojan horse names and their children, unless a bounded inert read is proven.
pub(super) const TROJAN_HORSES: &str = "\
    builtins importlib __builtins__ ctypes.pythonapi types.FunctionType types.CodeType \
    unittest.mock.patch mock.patch pytest.importorskip sys.__dict__ pkgutil pydoc runpy imp \
    zipimport code codeop timeit doctest marshal pickle _pickle shelve dill cloudpickle \
    inspect.getmodule gc.get_objects gc.get_referrers gc.get_referents";

/// Each trojan horse as one qualified name.
pub(super) fn trojan_horses() -> impl Iterator<Item = &'static str> {
    TROJAN_HORSES.split_whitespace()
}

/// The state of the import system: a reference is an import-system change.
pub(super) const STATE: [&str; 6] = [
    "site",
    "sys.path",
    "sys.meta_path",
    "sys.path_hooks",
    "sys.path_importer_cache",
    "sys.modules",
];

/// The builtin names that are trojan horses in any position: a plain name, the root of an attribute
/// chain or of a subscript, a value. `globals` and `locals` reach `__builtins__`, and
/// `breakpoint` imports the module that its hook names.
pub(super) const BUILTIN_TROJAN_HORSES: [&str; 10] = [
    "__import__",
    "exec",
    "eval",
    "compile",
    "__builtins__",
    "__loader__",
    "__spec__",
    "globals",
    "locals",
    "breakpoint",
];

/// The string values that name a trojan horse: `getattr(x, "__import__")` and `d["__builtins__"]`. A key
/// with one of them is never read as data.
pub(in crate::survey) const TROJAN_HORSE_STRINGS: [&str; 17] = [
    "__import__",
    "__builtins__",
    "import_module",
    "__subclasses__",
    "__globals__",
    "__self__",
    "__loader__",
    "__code__",
    "f_code",
    "gi_code",
    "cr_code",
    "ag_code",
    "f_builtins",
    "f_locals",
    "gi_frame",
    "cr_frame",
    "ag_frame",
];

/// The attributes that hand out a code object (AD-1048). `code.replace(co_names=...)` or
/// `type(code)(...)` then builds a function with other imports, and `f.__code__ = ...` runs it.
const CODE_OBJECT: [&str; 5] = ["__code__", "f_code", "gi_code", "cr_code", "ag_code"];

/// The fields of a code object that hold a scalar. A direct read of one hands out no code object;
/// `co_consts` can hold a nested code object, so it is not here.
const CODE_FIELD: [&str; 10] = [
    "co_name",
    "co_qualname",
    "co_filename",
    "co_firstlineno",
    "co_argcount",
    "co_posonlyargcount",
    "co_kwonlyargcount",
    "co_nlocals",
    "co_stacksize",
    "co_flags",
];

/// True when `attributes[at]` is a trojan horse on any value: the attributes of `ANY_ATTRIBUTE`, an import
/// function, a write to `__path__`, or a code object that does not end in a scalar field.
pub(super) fn attribute_trojan_horse(attributes: &[&str], at: usize) -> bool {
    let Some(name) = attributes.get(at) else {
        return false;
    };
    let code = CODE_OBJECT.contains(name)
        && !attributes
            .get(at + 1)
            .is_some_and(|field| CODE_FIELD.contains(field));
    code || ANY_ATTRIBUTE.contains(name) || IMPORT_FUNCTIONS.contains(name) || *name == "__path__"
}

/// The names of import functions: a trojan horse as a plain name or as an attribute of any value.
pub(super) const IMPORT_FUNCTIONS: [&str; 9] = [
    "__import__",
    "import_module",
    "load_module",
    "exec_module",
    "module_from_spec",
    "spec_from_file_location",
    "run_module",
    "run_path",
    "resolve_name",
];

/// The attributes that are hazards on any value: the attributes that reach the builtins, a
/// loader or the importer classes (`f.__globals__`, `len.__self__`, `object.__subclasses__`),
/// the state of the import system, and modules that another module can re-export (`os.sys`).
pub(super) const ANY_ATTRIBUTE: [&str; 21] = [
    "f_globals",
    "f_builtins",
    "f_locals",
    "gi_frame",
    "cr_frame",
    "ag_frame",
    "_getframe",
    "_current_frames",
    "currentframe",
    "__self__",
    "__globals__",
    "__subclasses__",
    "__loader__",
    "__spec__",
    "meta_path",
    "path_hooks",
    "path_importer_cache",
    "sys",
    "builtins",
    "importlib",
    "__builtins__",
];
