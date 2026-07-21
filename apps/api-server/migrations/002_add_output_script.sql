ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS output_script VARCHAR(16) NOT NULL DEFAULT 'original';

ALTER TABLE transcription_jobs
    DROP CONSTRAINT IF EXISTS transcription_jobs_output_script_check;

ALTER TABLE transcription_jobs
    ADD CONSTRAINT transcription_jobs_output_script_check
    CHECK (output_script IN ('original', 'traditional', 'simplified'));
