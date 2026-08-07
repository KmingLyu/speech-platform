ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS min_speakers INTEGER,
    ADD COLUMN IF NOT EXISTS max_speakers INTEGER;

ALTER TABLE transcription_jobs
    DROP CONSTRAINT IF EXISTS transcription_jobs_speaker_bounds_check;

ALTER TABLE transcription_jobs
    ADD CONSTRAINT transcription_jobs_speaker_bounds_check
    CHECK (
        (job_type = 'transcription' AND min_speakers IS NULL AND max_speakers IS NULL)
        OR (
            job_type = 'diarization'
            AND (min_speakers IS NULL OR min_speakers > 0)
            AND (max_speakers IS NULL OR max_speakers > 0)
            AND (min_speakers IS NULL OR max_speakers IS NULL OR min_speakers <= max_speakers)
        )
    );
