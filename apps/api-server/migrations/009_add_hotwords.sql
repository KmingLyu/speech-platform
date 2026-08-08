ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS hotwords TEXT[] NOT NULL DEFAULT '{}';
