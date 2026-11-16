# AD-668 A neutral crate names no language

**Status.** Accepted (owner order: the "best ratio" prevention bundle; new checks land as rules of
the self-contract, and their current FAIL rows stay visible). Part of #880. It amends AD-434.

**Reason.** Cut A says that a language rule lives in its collector and reaches the core as typed
facts. Up to now only a manual grep checked this, and it did not cover `store`. The hygiene audit
found a Dart SDK list and seven language branches in `store`. No rule of the contract could see them.

**Decision.**
1. The native contract forbids each neutral crate (`store`, `model`, `eval`, `report`, `core`) to
   name `Profile`, the vocabulary of the languages. The rules use the symbol form of
   `forbidden_dependency` (`target_symbol`) with the target `native`, so a re-export of `Profile` in
   another crate (`archkeel_collect::Profile`) is a use too. Two more rules forbid `store` to use its
   language modules `store.python` and `store.dart`.
2. A `target_symbol` rule judges an import as a use of the item in these cases:
   - the import names the item, by its own name or by a route hop of that name. A re-export under
     another name (`pub use vocab::Profile as Lang`) has such a hop.
   - the import is a glob (`*`). The scan does not list the names that a glob takes, so the import is
     undecided, not a PASS.
   - the route of the import is not proven to its end (AD-604), and some record of the reply binds
     the item under another name. Only such a record (`use a::Profile as Lang`, also in a macro body
     or in an unresolved import) can give the item a second name. A glob keeps the name. So when no
     record renames the item, the name of an import is the name of its item.
3. The Rust collector writes the item for a glob of an item (`use base::Profile::*`, the variants of
   an enum), as it writes it for the path. Before, it wrote `*`, as for a glob of a module.
4. A type alias is an item of its own (`pub type Alias = Profile;`). A use of the alias does not name
   `Profile`, in the same way as a function that returns the type. This is the meaning of the rule,
   not a gap: the alias itself names `Profile`, so an alias in a neutral crate is a violation.

**Why it is sound.** Before this record, three Rust forms gave a wrong PASS (a main binary, plants
of `tests/test_cli_native_rust_target_symbol.py`): a glob of the enum, a glob of the crate, and a
re-export under another name. The glob of the crate is now UNKNOWN, and the other two forms are FAIL.
A route that is not proven stays undecided while a renaming record exists. The renaming check reads
every record of the reply, also the macro bodies and the unresolved imports.

**Measured.** Native self-check: before 86 PASS, 0 FAIL, 0 UNKNOWN. After: 89 PASS, 4 FAIL,
0 UNKNOWN, 27 violations, pinned with issue #1384.
- `NATIVE-NEUTRAL-STORE-NO-PROFILE`: 21 rows.
- `NATIVE-NEUTRAL-STORE-NO-PYTHON-MODULE`: 4 rows.
- `NATIVE-NEUTRAL-STORE-NO-DART-MODULE`: 1 row.
- `NATIVE-NEUTRAL-CORE-NO-PROFILE`: 1 row.

The first form of item 2 made each route that is not proven undecided. That gave 3 UNKNOWN rules
(`model` 130, `eval` 29 and `report` imports undecided), although nothing in the workspace renames
`Profile`.

**Rejected.**
- A rule on the variants (`Profile::Dart`) only. The facts name the item and not the variant, and a
  `Self::Dart` or an alias route would hide the variant name.
- A target selector of `native.archkeel_facts` only. It does not see the re-export of `collect`,
  which `core` uses.

**Tests.**
- `tests/test_cli_native_rust_target_symbol.py`: 13 plants that rustc accepts.
- `tests/test_cli_native_python_target_symbol.py`: 4 plants that python3.12 runs. A star import is
  UNKNOWN.
- `tests/test_native_neutral_crates.py`: a token scan of each neutral crate is an independent oracle.
  Each module that names `Profile` is a pinned FAIL source, each pinned source still names it, and
  each language module of a neutral crate is the target of a rule.
