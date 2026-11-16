# AD-584 The clone check skips token runs that carry no logic

**Status.** Accepted. Part of #880. Builds on AD-327 (the clone ratchet).

**Decision.** `tools/rust_inert.py` marks the tokens of a Rust run that holds no logic. The
clone check in `tools/rust_clones.py` gives each marked token its own text, so no window that
holds one equals another window. Five kinds are marked, each by a strict rule:

1. A `use` item, from `use` to its `;`. An import list names things and computes nothing.
2. A `const` or `static` (not a `fn`) whose value is an array or a slice, with `&` allowed before
   it. Its tokens may be only literals, paths, commas, colons, brackets, parentheses, `&` and `-`.
   A name followed by `(` is a call and makes it logic.
3. A `mod name;` declaration, and a `struct` (with its attributes and `pub`) whose body holds
   only names, colons, `<`, `>`, `&`, `'`, brackets, `;` and commas. A literal or a call in the
   body makes it logic.
4. A declaration macro `name! { ... }` whose body holds only names, literals, brackets, commas
   and colons, and at least one `=` where each `=` is followed by a literal (for example
   `closed! { pub enum E { A = "a", } }`). A call in the body makes it logic.
5. A `match` whose body has arms of `path => literal` or a tuple of literals, or of
   `literal | literal => path`, with `_ => literal` or `_ => path` allowed as the last
   wildcard. A guard (`if`, `match` or `let` before the `=>`) or any other expression in an arm
   makes the whole `match` logic.

Everything else stays in the clone check. A table of rows that repeat by a period of up to 24
tokens is still skipped by the existing table rule, as before. Logic in the same file as a
table is still found: a copy of a function next to a copy of a table gives a block.

No clone may be added to `native/clone_baseline.json` to pass this check. A new block is a new
clone: share the code, or ask the owner of the baseline, who decides with the reason written
in the entry.

**Reason.** The check exists to find duplicated logic. The five kinds above repeat across Rust
files because they name things (an import list, an enum of words, a table of values, a struct
of plain fields), so two of them look alike without any logic being copied. Counting them as
clones put data into the production baseline. The rules stay strict so that a call, an
operator, a block, a guard or a second expression keeps the code visible to the check.

**Rejected.** Skipping whole files or whole modules by name: a clone of logic would hide with
them. Raising the window size: a real clone of a few lines would then pass. Allowing a call in a
table: a table of `K::new(i)` computes values, so it is logic.

**Checked by.** `tests/test_rust_clones.py` (a table, a use list, a match of variants and words,
declarations of words, names and fields are not clones; a call in a table, a macro body or a
match arm with a guard or an expression is logic; logic next to a table is still found).
