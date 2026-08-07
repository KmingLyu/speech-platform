ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS max_chars_per_line INTEGER;

UPDATE transcription_jobs
SET max_chars_per_line = 20
WHERE job_type = 'diarization' AND max_chars_per_line IS NULL;

ALTER TABLE transcription_jobs
    DROP CONSTRAINT IF EXISTS transcription_jobs_display_line_capacity_check;

ALTER TABLE transcription_jobs
    ADD CONSTRAINT transcription_jobs_display_line_capacity_check
    CHECK (
        (job_type = 'transcription' AND max_chars_per_line IS NULL)
        OR (job_type = 'diarization' AND max_chars_per_line > 0)
    );
