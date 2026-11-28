# AD-1496 A Python construct is decided for each module by the forms that can hide it

**Status.** Accepted. Issue #1537, release blocker. It amends [AD-737](ad-737-python-construct-support-is-one-map-with-downgrade-and-meet.md) and [AD-712](ad-712-a-written-typing-cast-call-is-a-partial-signal.md). Facts schema 11 gains one kind (`unseen_form`), additively.

**Reason.** The reply stated a construct `partial` for the whole run when one module had a form that could hide it. Three constructs (`cast`, `dynamic_import`, `any_annotation`) were `partial` always. Five (`hasattr`, `setattr`, `delattr`, `eval`, `exec`) were not read at all. A rule on Python could not reach PASS: CE had six such rules UNKNOWN, EE two (`NO-DYNAMIC-CONTRACT-BYPASS`). One hiding form in an exempt module also held the rules of every other module.

**Decision.**
1. The survey reads a site of `getattr`, `hasattr`, `setattr`, `delattr`, `vars`, `eval`, `exec`, `cast`, `dynamic_import` and `dunder_dict` in every module. A site is a record, so a found use is FAIL.
2. The reply states each of them `supported` (`Construct::PER_MODULE`). A module with a form that can hide a site gets one `unseen_form` record for each construct (the first form, with its place). The model holds a rule only when the rule judges that module and forbids that construct: the module is in the source and no `allowed_sources` or `exact_sources` entry names it. The cause is `a written form can hide a site of <construct> in <module>`.
3. The forms that hide a builtin call: the name used as a value or bound again; an attribute of that name (`x.eval`); a reach to the builtins (`__builtins__`, `builtins`, `globals`, `locals`, `compile`, `__self__`, `__globals__`, `f_globals`, `f_locals`, an import of `builtins`); a string literal that a call or a subscript reads and that names a builtin, `builtins` or `__dict__`; a text that runs (`eval`, `exec`) hides each builtin call.
4. `cast` and `dynamic_import`: a name or an attribute that is no callee of a recorded site (`cast`, an alias of `typing.cast`, the module `typing`, `x.cast`, `import_module`, `__import__`, the module `importlib`), and a star import from `typing` or `importlib`. The imports are read in the whole module, also inside a function.
5. A `# type: ignore` comment that no recorded statement carries hides `type_ignore`. A comment is a candidate only when it holds the words `type` and `ignore`.
6. An allowance (`allowed_sources`, `exact_sources`) that names code with a hiding form is not reported unused: the site can be there.
7. Stays run-wide partial, with its reason: `string_literal_compare` (needs the type of an operand), `any_annotation` (needs the premise that `typing` is unchanged; it needs a scan with no trojan horse site, so a declared site still holds it), `placeholder_body` (own coverage).

**Not covered (a limit, not a proof).** A builtin that a mapping holds and that a variable names (`ns[name](..)`, `getattr(x, name)` with `x` the builtins module from another module) is dynamic code. Door gaps hold `getattr` on an unproved receiver; the construct rule does not follow a name through a variable. A table of names, a comparison and a keyword `mode=` hold no lookup, so they hide nothing.

**Measured** (core of this change, v2 declarations). EE: 455 PASS, 24 UNKNOWN, 0 FAIL to 457, 22, 0 (both `NO-DYNAMIC-CONTRACT-BYPASS` PASS; the modules hold no `getattr`, `cast` or loader). CE with the outside script removed: `NO-REFLECTIVE-STATE` and `NO-UNPROVEN-CASTS` PASS; the other four are UNKNOWN with a named module: `evaluation` and `expression_globals` (the open sites of CE-ZERO). `NO-OPAQUE-ANNOTATIONS` waits for the `any_annotation` premise.

**Checked by.** `tests/test_cli_python_construct_coverage.py` (a site, a clean module and each hiding form for each construct; a form holds only the rule that judges its module). `native/python/src/survey/support_tests.rs`. `tests/test_cli_python_profile_limits.py`.
