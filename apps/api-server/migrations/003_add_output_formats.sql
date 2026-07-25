ALTER TABLE transcription_jobs
    ADD COLUMN IF NOT EXISTS output_formats TEXT[] NOT NULL
        DEFAULT ARRAY['json', 'txt', 'srt'];

UPDATE transcription_jobs
SET output_formats = ARRAY['json', 'txt', 'srt']
WHERE output_formats IS NULL;
