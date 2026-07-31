ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS job_type VARCHAR(32) NOT NULL DEFAULT 'transcription';

UPDATE transcription_jobs
SET job_type = 'transcription'
WHERE job_type IS NULL;

ALTER TABLE transcription_jobs
    DROP CONSTRAINT IF EXISTS transcription_jobs_job_type_check;

ALTER TABLE transcription_jobs
    ADD CONSTRAINT transcription_jobs_job_type_check
    CHECK (job_type IN ('transcription', 'diarization'));

CREATE INDEX IF NOT EXISTS idx_transcription_jobs_type_queue
    ON transcription_jobs (job_type, status, created_at);

CREATE OR REPLACE FUNCTION prevent_transcription_job_type_change()
RETURNS trigger AS $$
BEGIN
    IF OLD.job_type IS DISTINCT FROM NEW.job_type THEN
        RAISE EXCEPTION 'job_type is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS transcription_jobs_job_type_immutable ON transcription_jobs;

CREATE TRIGGER transcription_jobs_job_type_immutable
BEFORE UPDATE OF job_type ON transcription_jobs
FOR EACH ROW EXECUTE FUNCTION prevent_transcription_job_type_change();
