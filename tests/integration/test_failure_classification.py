import sys
from pathlib import Path


WORKER_ROOT = Path(__file__).resolve().parents[2] / "apps" / "worker"


def worker_failures():
    sys.path.insert(0, str(WORKER_ROOT))
    for module_name in list(sys.modules):
        if module_name == "src" or module_name.startswith("src."):
            del sys.modules[module_name]
    from src import failures

    return failures


def test_unexpected_errors_are_retryable_with_a_sanitized_message() -> None:
    failures = worker_failures()

    failure = failures.classify_failure(RuntimeError("psycopg: connection refused at 10.0.0.4"))

    assert failure.code == "processing_failed"
    assert failure.retryable is True
    assert "10.0.0.4" not in failure.message


def test_permanent_failures_are_never_retryable() -> None:
    failures = worker_failures()

    failure = failures.classify_failure(failures.source_unavailable("source file is missing"))

    assert failure.code == "source_unavailable"
    assert failure.retryable is False
    assert failure.message == "The requested source is unavailable."


def test_retryable_failures_keep_raw_detail_out_of_the_recorded_message() -> None:
    failures = worker_failures()

    error = failures.source_download_failed(
        "HTTP Error 503: Service Unavailable for https://youtu.be/example"
    )
    failure = failures.classify_failure(error)

    assert failure.retryable is True
    assert failure.message == "The source could not be downloaded."
    assert "503" in str(error)


def test_only_an_unacquirable_source_makes_a_download_failure_permanent() -> None:
    failures = worker_failures()

    permanent = [
        "ERROR: [youtube] abc: Video unavailable",
        "ERROR: [youtube] abc: Private video. Sign in if you have been granted access",
        "ERROR: [youtube] abc: Sign in to confirm your age",
        "ERROR: Unsupported URL: https://example.com/video",
    ]
    retryable = [
        "ERROR: unable to download webpage: timed out",
        "ERROR: [youtube] abc: Sign in to confirm you're not a bot",
        "ERROR: unable to download video data: connection terminated",
    ]

    assert [failures.download_failure(reason).failure.code for reason in permanent] == [
        "source_unavailable"
    ] * len(permanent)
    assert [failures.download_failure(reason).failure.retryable for reason in retryable] == [
        True
    ] * len(retryable)


def test_undecodable_media_is_permanent_while_transcoding_may_be_retried() -> None:
    failures = worker_failures()
    sys.path.insert(0, str(WORKER_ROOT))
    from src.media import MediaError, MediaProcessingError

    undecodable = failures.classify_failure(MediaError("moov atom not found"))
    transcoding = failures.classify_failure(MediaProcessingError("No space left on device"))

    assert undecodable.code == "media_unreadable"
    assert undecodable.retryable is False
    assert "moov atom" not in undecodable.message
    assert transcoding.code == "media_processing_failed"
    assert transcoding.retryable is True
    assert "No space left" not in transcoding.message
