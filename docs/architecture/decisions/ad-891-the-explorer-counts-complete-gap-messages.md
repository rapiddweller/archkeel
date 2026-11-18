# AD-891: The Explorer counts complete gap messages

The Explorer groups collection gap records by their complete recorded reason.
It counts the records and the distinct messages separately from rule verdicts.
It shows three frequent messages and lets the reader search and page through all messages.
One recorded location or subject is an example, not the complete evidence for the message.
The page does not infer causes or rule relationships from message text.
It shows whole-scan gap counts per UNKNOWN rule from the typed holds, without summing them.

The standalone page embeds the complete frame as compressed JSON from that same run.
The reader can download it without another scan.
An older payload can contain shortened reasons and no frame; the page does not reconstruct them.

The alternative of grouping on a colon loses qualified names and changes the reason.
Compression limits the cost of embedding the frame in the standalone page.
The Core frame remains the source for the download.

The report unit test checks full messages, counts and an example location.
The Explorer browser test checks search, pagination and the older payload.
