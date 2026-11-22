# AD-1042 A trojan horse reach names its reason, and narrow trojan horse forms are proposed

**Status.** Part accepted, part proposed. Part of #1963 (owner decisions of 2026-11-22). It amends [AD-664](ad-664-a-contract-can-declare-the-reach-of-a-door-site.md).

**Reason.** EE and CE run code that they parse from XML. That is a product function, not the architecture of their own code. They must declare such a site as an exception with a reason, and then the rules can PASS. A reader of the verdict must see which declarations the PASS rests on.

**Built in this change.**
1. Each applied declaration carries its `rationale` (the field was required and unused after the read). The frame row `trojan_horse_reach[]` has the key `rationale` (schema `archkeel-core-frame-1`). The text list prints `Reason: ...` under the line of the site.
2. The verdict text keeps "PASS assuming the declared reach of N trojan horses". The frame keeps `assumed` for each rule. Both exist since AD-664.
3. A declaration that matches no trojan horse is a defect row (`trojan_horse_reach.unmatched`), never ignored. This is AD-664 and is unchanged.
4. The self-check of `native/` has no declaration. A test fails when one appears.

**Where a declaration lives.** The root contract (`declarations.trojan_horse_reach`). The cheapest option is to keep it there. The contract digest covers it, it has an id and a provenance, and the model reads no other file. A copy in `archkeel.toml` needs a second reader, a second schema and a second digest rule, and the declaration would leave the reviewed contract. That is a second source of truth, so it is not built.

**Proposed, not built: narrow trojan horse forms.** The collector proves first what it can. It cannot prove these, so they need a declaration (a new contract version 3.20.0 and `archkeel-facts` 12, because the published schemas list the form words):
- `trojan_horse_module`: the import statement of `pickle`, `dill`, `pkgutil` or a trojan horse module whose uses stay open. Premise: the module object reaches only declared trojan horses.
- `pickler`: `pickle.dump(s)`, `dill.dumps`, `Pickler`. Python imports the module named by the `__module__` of a pickled function, so this is a real trojan horse. Premise: the pickled objects name only modules below `loads`.
- `walk_packages`: `pkgutil.walk_packages` outside the registry shape. Premise: the names start with the prefix of the call and below `loads`.
- `subclasses`: `__subclasses__` on a receiver that is not a proven project class. Premise: the classes reached start no import that is not below `loads`.
- `trojan_horse_string`: a string that names a trojan horse. Premise: the text is no argument of `getattr`, `__import__` or a subscript of a namespace. Several strings on one line need a count in the declaration, or the declaration is `ambiguous`.

**Measured** (EE `560d5c7ef`, scratch copy, 21 draft declarations, the build of this change). Declarations only: 223 UNKNOWN stay, because 49 gaps have no form. With the proposed forms emulated by a patch: 50 UNKNOWN (173 freed), 0 FAIL when the declared `loads` are empty, 4 FAIL when the registries declare their real `loads`. A FAIL names its declaration. 173 rules read "PASS assuming".

**Tests.** `tests/test_cli_python_trojan_horse_reach.py` (the reason in the frame and the text, the self-check has none).
