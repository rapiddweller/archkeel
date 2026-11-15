# AD-580: A declared signature that names a type reaches its public entry

## Status

Accepted. Part of #880. It amends AD-514 and uses the signature shapes of AD-550.

## Decision

Release 4.0.1 counts a `public` entry as used when a declared facade signature names its type (`facade_types`, AD-65).
AD-514 kept the row `interface.usage_unknown` for that case, because the core read no signature.
The core now reads it where the collector wrote the facts.

A `public` entry of the contract covers a function, a class or a module (the rules of AD-550).
For each covered function, and each public method of a covered class, the written types of the parameters and the return are read from the shapes.
Each name with a proven binding (a defined or imported name) is recorded as the name that the signature writes, and as the definition that its one plain import route reaches.
The entry `module:Name` is used when a recorded name is `module.Name`.
The entry `module` is used when a recorded name lies in that module.
Collections, unions, annotated types and the head and arguments of a user generic are read down to their names.

The run reads the shapes when the contract tree has an `interface_boundary` rule (`Need::InterfaceBoundary`).
A run without shapes (TypeScript, Rust, Dart) reads no signature and keeps its rows.
Planned entries are not changed: the rule applies to `public` entries.

## Kept rows

A signature that the collector cannot prove names nothing: a private function, a string annotation, a name under `TYPE_CHECKING`, a decorated function, a method of a class with no record.
The row stays `interface.usage_unknown`. In four of these forms 4.0.1 clears the entry; the core never clears one that 4.0.1 refuses.

## Limit measured on DATAMIMIC CE

The shapes exist only where a symbol record exists (AD-518).
A class has no members when its name escapes (rule 7), when it has a base outside the twelve builtins, `Protocol` and `enum`, or a decorator.
A property or another decorated method has no record.
On CE this keeps about 45 of the 72 entries that 4.0.1 reaches only by a signature.
A read of the class body that ignores these escapes states what is written, not what the class has at run time; it needs an owner decision.
