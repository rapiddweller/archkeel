# AD-891: The Explorer counts complete gap messages

AD-920 removes the global message list from the fact sheet. The gap-record download remains.

The Explorer groups collection gap records by their complete recorded reason.
It counts the records and the distinct messages separately from rule verdicts.
It shows three frequent messages and lets the reader search and page through all messages.
One recorded location or subject is an example, not the complete evidence for the message.
The page does not infer causes or rule relationships from message text.
It shows whole-scan gap counts per UNKNOWN rule from the typed holds, without summing them.

The standalone page embeds every gap record from that same run and its referenced locations.
The reader can download these records without another scan.
The download is not the complete run frame.
An older payload can contain shortened reasons and no frame; the page does not reconstruct them.

The alternative of grouping on a colon loses qualified names and changes the reason.
The page stores repeated gap strings once to limit the size of the embedded frame.
The Core frame remains the source for the download.

The report unit test checks full messages, counts and an example location.
The Explorer browser test checks search, pagination and the older payload.
