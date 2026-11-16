# AD-624: The system report keeps part ownership and unchecked interfaces

## Context

A system can have parts with different layer orders over the same layer names.
More than one interface can connect the same parts.
The system reader checks that an interface schema file exists.
It does not check the data exchanged between the parts.

## Decision

The system topology names the owning part of each layer order.
The report uses the order of that part only.
An interface edge carries the interface id and has an UNKNOWN status.
The Explorer gives each interface a distinct graph and layout id.
The interface tooltip says that the interface is not checked.
The system verdict continues to describe the checks on its parts.

## Alternatives and limit

Matching layer names cannot identify the owning part.
A PASS interface edge would claim a check that does not exist.
This decision does not add a check of exchanged data.

## Checks

The system report plant uses opposite orders and two interfaces with an unrelated schema.
The Explorer scene test checks both graph ids and layout ids.
The report tests check the layer ranks and the interface statuses.
