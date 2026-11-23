// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that are trojan horses or state of the import system (AD-450, AD-472).

/// The named gaps of the sites.
pub(in crate::survey) const DYNAMIC: &str = "dynamic_import";
pub(in crate::survey) const IMPORT_SYSTEM: &str = "import_system_change";
/// A proven literal import call: a static edge, not a gap (AD-472, `literal.rs`).
pub(in crate::survey) const LITERAL: &str = "literal_import";

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
    if let Some(module) = name.strip_suffix(".*") {
        return held_by(module);
    }
    let under = |entry: &&str| {
        name == *entry
            || name
                .strip_prefix(*entry)
                .is_some_and(|rest| rest.starts_with('.'))
    };
    if STATE.iter().any(under) {
        Some(IMPORT_SYSTEM)
    } else if trojan_horses()
        .chain(importers())
        .any(|entry| under(&entry))
    {
        Some(DYNAMIC)
    } else {
        None
    }
}

/// The gap of a star import of `module`: a hazard name that the module holds directly is bound.
fn held_by(module: &str) -> Option<&'static str> {
    let direct = |entry: &&str| {
        entry
            .rsplit_once('.')
            .is_some_and(|(parent, _)| parent == module)
    };
    if STATE.iter().any(direct) {
        Some(IMPORT_SYSTEM)
    } else if trojan_horses()
        .chain(importers())
        .any(|entry| direct(&entry))
    {
        Some(DYNAMIC)
    } else {
        None
    }
}

/// The name of a star import of `module`: the module, or `module.*` when the module is no hazard
/// itself and holds hazard names (`from logging.config import *` binds `dictConfig`).
pub(super) fn star(module: &str) -> String {
    if hazard(module).is_none() && held_by(module).is_some() {
        format!("{module}.*")
    } else {
        module.to_owned()
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

/// The standard library names that import a module by a string, run a text, or hand out a code
/// object (AD-1059), with their children. Unlike `TROJAN_HORSES`, a module above one of them is no
/// site as a value: `getattr(logging, level)` and `logging.Handler.__init__(self)` are ordinary,
/// and the access forms that reach `logging.config` from the value are sites already.
const IMPORTERS: &str = "\
    logging.config \
    unittest.TestLoader unittest.defaultTestLoader unittest.loader.TestLoader \
    unittest.loader.defaultTestLoader unittest.main unittest.TestProgram unittest.main.TestProgram \
    dis.Bytecode dis.get_instructions dis._get_code_object inspect.dis modulefinder.dis \
    pdb.dis trace.dis sre_compile.dis profile.run profile.runctx profile.Profile cProfile.run \
    cProfile.runctx cProfile.Profile trace.Trace bdb.Bdb pdb.run pdb.runeval pdb.runctx pdb.Pdb \
    xml.sax.make_parser xml.sax._create_parser multiprocessing.spawn warnings._setoption \
    warnings._getcategory warnings._processoptions";

/// Each hazard name that is not above-checked, as one qualified name.
fn importers() -> impl Iterator<Item = &'static str> {
    IMPORTERS.split_whitespace()
}

/// Each trojan horse as one qualified name.
pub(super) fn trojan_horses() -> impl Iterator<Item = &'static str> {
    TROJAN_HORSES.split_whitespace()
}

/// The standard library calls that import the module that an argument names, with the parameters
/// that carry the name. `unittest.main()` reads its names from the command line, which is outside
/// the scan, and `xml.sax.make_parser()` uses its default parsers.
const NAMED_BY_ARGUMENT: [(&str, &[&str]); 4] = [
    ("unittest.main", &["module", "defaultTest", "argv"]),
    ("unittest.TestProgram", &["module", "defaultTest", "argv"]),
    (
        "unittest.main.TestProgram",
        &["module", "defaultTest", "argv"],
    ),
    ("xml.sax.make_parser", &["parser_list"]),
];

/// The keywords that carry a module name when `qualified` is a call that imports a module only if
/// an argument names it. `None` for each other name.
pub(super) fn named_by_argument(qualified: &str) -> Option<&'static [&'static str]> {
    NAMED_BY_ARGUMENT
        .iter()
        .find_map(|(name, keywords)| (*name == qualified).then_some(*keywords))
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
/// `breakpoint` imports the module that its hook names. `help("a.b")` imports the module `a.b`.
pub(super) const BUILTIN_TROJAN_HORSES: [&str; 11] = [
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
    "help",
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
