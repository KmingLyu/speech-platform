ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS diarization_model VARCHAR(128),
    ADD COLUMN IF NOT EXISTS diarization_model_revision VARCHAR(256);

ALTER TABLE transcription_jobs
    DROP CONSTRAINT IF EXISTS transcription_jobs_diarization_model_check;

ALTER TABLE transcription_jobs
    ADD CONSTRAINT transcription_jobs_diarization_model_check
    CHECK (
        (job_type = 'transcription' AND diarization_model IS NULL AND diarization_model_revision IS NULL)
        OR (
            job_type = 'diarization'
            AND diarization_model IS NOT NULL
            AND diarization_model_revision IS NOT NULL
            AND length(diarization_model_revision) > 0
        )
    );
