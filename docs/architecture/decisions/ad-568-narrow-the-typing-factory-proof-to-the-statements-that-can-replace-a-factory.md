# AD-568: Narrow the typing factory proof to the statements that can replace a factory

## Status

Accepted for the Python import survey. Part of #880. It narrows AD-552 and extends AD-566.

## Decision

AD-552 withheld the proof of a typing alias when the scan had any attribute store.
Each `self.x = v` of a method did that, so the proof never held on a real project.
The survey now withholds it only when the scan holds a statement that can replace what a factory makes:

1. A store or a delete of an attribute named like a `typing` factory (`Annotated`, `Optional`, `Union`, `Literal`, `TypeVar`, `NewType`), like a name of the table below, or `__getitem__`, `__class_getitem__`, `__call__`, `__dict__`, `__class__` or `__new__`.
2. A `setattr` or `delattr` call, and each use of `__setattr__` or `__delattr__`.
   One form is harmless: `object.__setattr__(a, "name", v)` with a literal name that is none of the names of point 1.
   `object.__setattr__` works on a module, so a computed name is not harmless.
3. A write through `vars(..)` or through the result of a `__dict__` read.
   A read is only an unpack `**d`, a comparison, an iteration, a subscript load, `len`, `list`, `dict`, `sorted`, `tuple`, `set`, or `keys`, `items`, `values`, `get`, `copy`.
4. A write into `sys.modules`, except a store with a literal key that is none of `typing`, `typing_extensions` and the modules of the table below.

`Annotated[X, m]`, `Optional[X]` and `Literal[..]` make an alias for any arguments.
`Union` keeps the literal-argument condition, because `Union[X]` and `Union[X, X]` are `X`.

The same guard now covers the call of a standard library value class.
These calls make a value in Python 3.12, never a module:
`pathlib.Path`, `PurePath`, `PurePosixPath`, `PureWindowsPath`, `decimal.Decimal`, `fractions.Fraction`, `uuid.UUID`,
`datetime.date`, `datetime`, `time`, `timedelta`, `timezone`, `logging.getLogger`,
`collections.OrderedDict`, `defaultdict`, `Counter`, `deque`.
The name must be the one plain import of its module, and no scanned module may have the name of that module.

## Reason

On DATAMIMIC CE, one `PurePosixPath(...)` constant withheld 99 routes through `authoring.domain.requests`.
Twelve `Annotated[X, Field(...)]` aliases withheld the modules of their authors.

## Checks and limits

`uses_typing_guard_tests.rs` has the forms of each point with Python 3.12 truth:
`setattr`, `object.__setattr__`, `vars(typing)[..]`, `typing.__dict__.update` and a swapped `sys.modules` entry each change `typing.Annotated` or the next import of `typing`.
A write that reaches a module through a name that the scan cannot read is a named gap of AD-450, not a proof.
A union of imported types, an attribute of a module, a call of an external callable and a module with a namespace hazard keep their escape.
