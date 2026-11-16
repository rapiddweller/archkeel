# AD-620: The system document states each part and the interface between the parts

Status: accepted (owner order). Part of #880. It amends AD-616 and AD-618.

Every unit has a written responsibility. A part of the system document states, in lists of text,
what the part is responsible for, what it is not responsible for, and what it provides. A part with
an empty list refuses the run. The Explorer shows these texts for the part box (responsibility, not
responsible for, provides).

The document has a list `interfaces`. An interface joins two parts by id, has a title, and names a
schema file of the repository that must exist. It is no import: the shell starts the core binary and
reads its frame, so the report draws it as an edge without import sites, named by its title, and it
is neither a deviation nor an allowed-but-unused requirement. The frame states it in `system.interfaces`.
ArchKeel states one: "Core frame protocol", `schema/archkeel-core-frame-1.schema.json`.

The report opens a diagram that is wider than the window at 60% at least, and not smaller, so the
titles of the boxes can be read; the rest of the diagram is one pan away.

Limit: the core checks that the schema file exists. It does not check that the frames that the
shell reads fit it; the shell does that for each run.
