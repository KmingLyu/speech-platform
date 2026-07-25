"""Classification of Transcription job failures into Retryable and Permanent."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Failure:
    """How one failed Attempt is recorded on its Transcription job."""

    code: str
    message: str
    retryable: bool


class ClassifiedFailure(RuntimeError):
    """A failure that already knows whether another Attempt could recover from it.

    ``message`` is the sanitized text exposed through the API; ``detail`` keeps the
    raw tool output for the Worker log only.
    """

    retryable: bool

    def __init__(self, code: str, message: str, *, detail: str | None = None) -> None:
        super().__init__(detail or message)
        self.failure = Failure(code=code, message=message, retryable=self.retryable)


class PermanentFailure(ClassifiedFailure):
    retryable = False


class RetryableFailure(ClassifiedFailure):
    retryable = True


UNEXPECTED_RETRYABLE_FAILURE = Failure(
    code="processing_failed",
    message="Transcription processing failed.",
    retryable=True,
)

PERMANENT_DOWNLOAD_REASONS = (
    "video unavailable",
    "private video",
    "removed by the uploader",
    "has been terminated",
    "does not exist",
    "unsupported url",
    "is not a valid url",
    "members-only",
    "sign in to confirm your age",
    "age-restricted",
    "no video formats found",
    "requested format is not available",
    "copyright claim",
)


def classify_failure(error: BaseException) -> Failure:
    """An unexpected error is Retryable: the environment may recover, and the
    automatic-attempt budget keeps it from looping."""
    if isinstance(error, ClassifiedFailure):
        return error.failure
    return UNEXPECTED_RETRYABLE_FAILURE


def source_unavailable(detail: str) -> PermanentFailure:
    return PermanentFailure(
        "source_unavailable",
        "The requested source is unavailable.",
        detail=detail,
    )


def source_download_failed(detail: str) -> RetryableFailure:
    return RetryableFailure(
        "source_download_failed",
        "The source could not be downloaded.",
        detail=detail,
    )


def download_failure(reason: str) -> ClassifiedFailure:
    """Classify a Source download error by whether any Attempt could acquire it.

    Only reasons that name the Source itself as gone, private, or unsupported are
    Permanent; everything else is treated as transport and stays Retryable.
    """
    lowered = reason.lower()
    if any(marker in lowered for marker in PERMANENT_DOWNLOAD_REASONS):
        return source_unavailable(reason)
    return source_download_failed(reason)
