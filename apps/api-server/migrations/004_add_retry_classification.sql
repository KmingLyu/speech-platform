ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS automatic_attempt_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS error_retryable BOOLEAN;

UPDATE transcription_jobs
SET automatic_attempt_count = attempt_count
WHERE automatic_attempt_count = 0 AND attempt_count > 0;
