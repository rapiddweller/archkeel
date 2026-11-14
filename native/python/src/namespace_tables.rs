// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shared namespace exposure names of the Python collector.

pub(crate) const GLOBAL: [&str; 9] = [
    "globals",
    "builtins.globals",
    "exec",
    "builtins.exec",
    "eval",
    "builtins.eval",
    "__builtins__",
    "__import__",
    "builtins.__import__",
];
pub(crate) const LOCAL: [&str; 4] = ["locals", "vars", "builtins.locals", "builtins.vars"];
pub(crate) const GLOBALS: [&str; 2] = ["globals", "builtins.globals"];
pub(crate) const CONTAINERS: [&str; 6] = ["set", "frozenset", "sorted", "list", "tuple", "len"];
#[cfg(any(test, feature = "dump"))]
pub(crate) const TYPE_READERS: [&str; 3] = [
    "typing.get_type_hints",
    "typing_extensions.get_type_hints",
    "inspect.get_annotations",
];
#[cfg(any(test, feature = "dump"))]
pub(crate) const OWN: [&str; 7] = [
    "exec",
    "builtins.exec",
    "eval",
    "builtins.eval",
    TYPE_READERS[0],
    TYPE_READERS[1],
    TYPE_READERS[2],
];
