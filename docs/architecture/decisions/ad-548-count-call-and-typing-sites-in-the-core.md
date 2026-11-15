# AD-548: Count call and typing sites in the core

## Status

Accepted. Part of #880.

## Decision

The collector counts every call expression in every selected parsed file. Nested calls and calls
in decorators count. A decorator without a call does not count. The count has one row per file.
The model checks the selected inventory, each row sum, and the proven call records. It does not
give a measure when a file or row is missing, duplicated, or inconsistent. The frame shows the
measure. This decision does not compare a baseline or change a rule verdict.

A call is resolved when an AD-520 site proves a target, or when a sole plain import and an AD-518
symbol record prove it. A partially resolved construction is a separate class. A stable import
from outside the scan is external. A name in the fixed builtin set is builtin only when no name
binding in the file can hide it. Every other call is unresolved. A receiver call such as
`self.m()` is unresolved unless a module import proves the receiver. The file-wide binding check
can withhold a proof that a more precise scope could make; it cannot add a target proof.

The typing count includes a missing parameter or return annotation of a public definition, a
position whose written annotation contains `object` or `Any`, and a dynamic typing call. Names
starting with an underscore are not public. The first parameter of an undecorated method named
`self` or `cls` is not a position. A decorated method has no proven receiver. A written call to
`getattr`, `eval`, or `exec` counts even if a binding may
hide the builtin. A written `cast` call counts when a plain `typing` import names it. These
conservative counts can include a site that a more precise scope would exclude.

The private count includes a read of an underscore attribute, including an augmented assignment.
It excludes a method receiver or a uniquely bound module import. Other profiles have no rows and
no measure. A measure is a count,
not a claim that the source is complete in any other respect.

## Reason and limits

The 4.0.1 call and typing numbers depend on the interpreter and use inference. The core needs
counts that do not claim an unproved target. Counting only the AD-520 site records misses calls
outside admitted definitions. Reusing those records and the existing binders avoids a second
scope analysis. The new measure has different definitions and must not be compared with a 4.0.1
baseline as if the numbers were equal.

Tests cover nested and decorated calls, rebound names, receiver calls, typing positions, missing
rows, invalid sums and file-order determinism. The measure does not enforce a budget.
