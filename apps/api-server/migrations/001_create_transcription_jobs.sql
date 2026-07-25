CREATE TABLE transcription_jobs (
    id VARCHAR(40) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    current_stage VARCHAR(32),
    source_type VARCHAR(16) NOT NULL CHECK (source_type IN ('upload', 'youtube')),
    source_url TEXT,
    original_filename TEXT,
    source_path TEXT,
    model VARCHAR(64) NOT NULL,
    language VARCHAR(16),
    output_formats TEXT[] NOT NULL DEFAULT ARRAY['json', 'txt', 'srt'],
    output_script VARCHAR(16) NOT NULL DEFAULT 'original'
        CHECK (output_script IN ('original', 'traditional', 'simplified')),
    duration DOUBLE PRECISION,
    processed_seconds DOUBLE PRECISION,
    result_text TEXT,
    result_json_path TEXT,
    result_txt_path TEXT,
    result_srt_path TEXT,
    worker_id VARCHAR(128),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    heartbeat_at TIMESTAMPTZ,
    error_code VARCHAR(64),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_transcription_jobs_queue
    ON transcription_jobs (status, created_at);
