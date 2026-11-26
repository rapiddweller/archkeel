# AD-1191: A class gets a kind from a base in another project module

Status: accepted. Amends AD-518 (rule 6). Closes #2129. This change adds symbol records, so it can turn UNKNOWN
into PASS or FAIL for rules that read classes (`boundary_types`). It needs a verification run.

## Why

AD-518 rule 6 gave a class a kind only when each base was a builtin, a name of `typing` or `enum`, or a class of
the same module. A base from another module gave no kind and no record. Measured on CE `23bd48d9`: about 59
classes of the public facades had no record for this reason, among them `AppendConverter(Converter)` and
`BankAccount(BaseEntity)`. 50 of the 59 stop at `abc.ABC`.

## Decision

1. A base that is a name of another module of the scan has the kind of that class, when each step is proven:
   - the base is written as the one plain `from m import C` (or `import m` with `m.C`) of the importing module
     (the binding is the sole binder of its name, at module level, no relative import);
   - each module on the route (`m` and the modules that re-export `C`, at most 8 hops) is a module that the
     survey admits: no hazard site and no escape of its namespace;
   - each re-export is the one plain `from m2 import C` of that module;
   - the last module defines `C` with one `class` statement that binds the name once, has no decorator, no
     keyword and no type parameter, and whose bases have a kind by the same rule.
2. The kind of each class is found to a fixpoint over the admitted modules. A round only adds classes, so a stop
   at 16 rounds loses precision and nothing else. The record of the derived class names the module that defines
   the base (`app.base.Base`), not the re-exporting module.
3. `abc.ABC` is a base that gives a plain class (its metaclass `ABCMeta` gives a class and no other base here has a
   metaclass). It is read like a name of `enum` or `typing`.
4. A class of another module is never `constructible`: the survey claims no `A()` instance for it.
5. Not changed: a decorated class, a keyword (`metaclass=`), a computed base (`importlib`, a call, a conditional),
   a relative import and a base outside the scan keep no kind and no record. `boundary_types` still names the
   inherited surface of a base that has a record (`inherited_surface`): the verdict stays UNKNOWN there.

## Why it is sound

A kind is a property of one class statement. The statement of a base is read once: it binds its name once, in the
module body, without a decorator or a keyword, and each of its bases is proven in turn. The route is read in the same
way: each hop is the one statement that binds the name. A module that a hazard or an escape withholds is outside the
route (`admitted`), as for the proofs of AD-504 and AD-550. A write through `sys.modules` or a computed import is a
survey gap that holds the rules (AD-450); this record does not remove it.

## Measured (`ARCHKEEL_ALLOW_BUILD=1`, same revision, without and with the change)

| | without | with |
|---|---|---|
| CE `23bd48d9`, outside script emptied: class records | 105 | 326 (+221) |
| CE rule verdicts | 176 PASS / 99 UNKNOWN / 1 FAIL | same |
| CE `boundary_type_position` gaps | 291 (`no_record` 254, `member_no_record` 5) | 291 (`no_record` 236, `member_no_record` 23) |
| EE `560d5c7ef`: class records | 296 | 448 (+152) |
| EE rule verdicts | 256 PASS / 223 UNKNOWN | same |

With the outside script in place, CE withholds all 540 modules (#2099), so nothing changes there. The CE rules stay
UNKNOWN because of other causes: the facade escape (#2106), decorated classes (#2130), members without a record and the
68 dynamic-import gaps.

## Tests

- `native/python/src/survey/declared/kind_tests.rs`: the table, the re-export, the three-module fixpoint, a name that two
  statements bind, a module that is not admitted, a decorator, a keyword, a call, a conditional, an enum and a protocol, a
  relative import and a computed base.
- `tests/test_cli_python_class_kind_project.py`: 15 plants through the core. Each runs under CPython, and the output shows what
  the class really is: a base rebound by a write, rebound in the facade, a metaclass, a base built by a call, a conditional base,
  a decorated base that is replaced, `importlib`, two binders, a module with a hazard, a relative import.
