// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::FileMode;
use crate::source_input::Suffix;

#[test]
fn the_mode_of_a_file_comes_from_its_suffix_and_its_module_syntax() {
    let of = |suffix, syntax| FileMode::of(Some(suffix), syntax);
    // A declaration file stays a declaration file, with or without module syntax.
    assert_eq!(of(Suffix::Dts, false), FileMode::Declaration);
    assert_eq!(of(Suffix::Dts, true), FileMode::Declaration);
    // Module syntax, or a suffix that fixes the format, makes a module.
    assert_eq!(of(Suffix::Ts, true), FileMode::Module);
    assert_eq!(of(Suffix::Js, true), FileMode::Module);
    assert_eq!(of(Suffix::Mjs, false), FileMode::Module);
    assert_eq!(of(Suffix::Cts, false), FileMode::Module);
    // A JavaScript file without module syntax or format is a global script.
    assert_eq!(of(Suffix::Js, false), FileMode::Script);
    assert_eq!(of(Suffix::Jsx, false), FileMode::Script);
    // A TypeScript file without module syntax, and no suffix, collect no script facts.
    assert_eq!(of(Suffix::Ts, false), FileMode::ClearedScript);
    assert_eq!(FileMode::of(None, false), FileMode::ClearedScript);
    assert_eq!(FileMode::default(), FileMode::ClearedScript);
}

#[test]
fn only_a_script_is_cleared_and_each_mode_answers_the_old_booleans() {
    assert_eq!(FileMode::Script.cleared(true), FileMode::ClearedScript);
    assert_eq!(FileMode::Script.cleared(false), FileMode::Script);
    for other in [
        FileMode::Declaration,
        FileMode::Module,
        FileMode::ClearedScript,
    ] {
        assert_eq!(other.cleared(true), other);
    }
    // (module_file, declaration_file, script_mode) of each mode, with the module syntax apart.
    let flags = |mode: FileMode, syntax| {
        (
            mode.is_module(syntax),
            mode.is_declaration(),
            mode.is_script(),
        )
    };
    assert_eq!(flags(FileMode::Declaration, false), (false, true, false));
    assert_eq!(flags(FileMode::Declaration, true), (true, true, false));
    assert_eq!(flags(FileMode::Module, false), (true, false, false));
    assert_eq!(flags(FileMode::Script, false), (false, false, true));
    assert_eq!(flags(FileMode::ClearedScript, true), (false, false, false));
}
