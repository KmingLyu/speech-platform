# Do not store diarization text in the database

**Status: accepted**

Jobs created through `POST /v1/diarizations` must leave `transcription_jobs.result_text` as `NULL`. Their transcript and diarized transcript outputs are stored as requested file artifacts using the existing result filenames and `result_*_path` database columns for now. Existing `POST /v1/transcriptions` behavior remains unchanged for now.

The `result_text` column is a deferred cleanup item. After the transcription API and all readers/tests use artifact files instead of the database copy, a later migration should remove the column and its write/read paths. A separate future artifact-naming migration should then rename the existing result filenames and `result_*_path` columns to the generic `output.*` and `output_*_path` names, with compatibility handling for existing jobs. This staged migration avoids expanding the current diarization work while preventing new diarization results from adding more duplicated text.

**Deferred cleanup**

- [ ] Stop writing and reading `transcription_jobs.result_text` for transcription jobs.
- [ ] Rename existing `result.json`, `transcript.txt`, and `transcript.srt` conventions to the agreed generic `output.*` names.
- [ ] Rename `result_json_path`, `result_txt_path`, and `result_srt_path` to `output_json_path`, `output_txt_path`, and `output_srt_path` with a safe migration and compatibility plan.
