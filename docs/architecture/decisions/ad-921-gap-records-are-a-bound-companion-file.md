# AD-921: Gap records are a bound companion file

This decision amends AD-891. The report no longer embeds the gap records.
The shell writes the same run's frame as a JSON companion beside the HTML.
The HTML names the gap count, the file and the SHA-256 of its bytes.
The file name contains that digest. A matching existing file can be reused.
A link and a warning tell the reader to keep the two files together.

The shell writes the companion before the HTML. It refuses an unsafe report target first.
If writing the HTML then fails, the companion can remain. The shell does not delete it.
The HTML never claims that a missing file is present.
An HTML page made without the shell says that the companion is unavailable.
JSON output and reports without an output file do not create a companion.

The embedded export exceeded the native report size budget. Raising the budget was rejected.
The native core stays the source of the frame and does not add a compression dependency.
Tests check the digest, the 420-record example, unsafe targets and unchanged JSON output.
