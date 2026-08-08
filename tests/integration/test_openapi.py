import sys
from pathlib import Path


API_SERVER_ROOT = Path("/workspace/apps/api-server")


def test_hotwords_are_documented_as_repeated_multipart_values(tmp_path: Path) -> None:
    sys.path.insert(0, str(API_SERVER_ROOT))
    from src.config import Settings
    from src.main import create_app

    app = create_app(
        settings=Settings(
            database_url="postgresql://unused",
            data_root=tmp_path,
            max_upload_size_bytes=1024,
        ),
        migrate=lambda: None,
    )

    schema = app.openapi()
    for path in ("/v1/transcriptions", "/v1/diarizations"):
        encoding = schema["paths"][path]["post"]["requestBody"]["content"][
            "multipart/form-data"
        ]["encoding"]["hotwords"]

        assert encoding == {"style": "form", "explode": True}
