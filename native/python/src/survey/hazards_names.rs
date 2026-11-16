// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that are doors or state of the import system (AD-450, AD-472).

/// The named gaps of the sites.
pub(in crate::survey) const DYNAMIC: &str = "dynamic_import";
pub(in crate::survey) const IMPORT_SYSTEM: &str = "import_system_change";
/// The door names and their children, unless a bounded inert read is proven.
pub(super) const DOORS: &str = "\
    builtins importlib __builtins__ ctypes.pythonapi types.FunctionType types.CodeType \
    unittest.mock.patch mock.patch pytest.importorskip sys.__dict__ pkgutil pydoc runpy imp \
    zipimport code codeop timeit doctest marshal pickle _pickle shelve dill cloudpickle \
    inspect.getmodule gc.get_objects gc.get_referrers gc.get_referents";

/// Each door as one qualified name.
pub(super) fn doors() -> impl Iterator<Item = &'static str> {
    DOORS.split_whitespace()
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

/// The builtin names that are doors in any position: a plain name, the root of an attribute
/// chain or of a subscript, a value. `globals` and `locals` reach `__builtins__`, and
/// `breakpoint` imports the module that its hook names.
pub(super) const BUILTIN_DOORS: [&str; 10] = [
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

/// The string values that name a door: `getattr(x, "__import__")` and `d["__builtins__"]`.
pub(super) const DOOR_STRINGS: [&str; 7] = [
    "__import__",
    "__builtins__",
    "import_module",
    "__subclasses__",
    "__globals__",
    "__self__",
    "__loader__",
];

/// The names of import functions: a door as a plain name or as an attribute of any value.
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
pub(super) const ANY_ATTRIBUTE: [&str; 13] = [
    "f_globals",
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
