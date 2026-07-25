# Use cursor pagination for transcription job history

**Status: accepted**

`GET /v1/transcriptions` uses an opaque cursor with a stable `(created_at, id)` ordering and a bounded `limit`, returning `items` and `next_cursor`. Cursor pagination avoids page drift, duplicate rows, and skipped jobs when new Transcription jobs are created while a caller is reading history; total counts and arbitrary page jumps are not part of the MVP contract.

**Considered Options**

- Offset and page-number pagination: simpler to explain, but new or deleted jobs can shift pages and cause duplicates or omissions.
- Cursor pagination: slightly more complex, but stable for an append-heavy asynchronous job history, therefore adopted.
