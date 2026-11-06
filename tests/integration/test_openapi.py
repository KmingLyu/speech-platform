import os

import httpx


def test_hotwords_are_documented_as_repeated_multipart_values() -> None:
    # Query the running API instead of importing its shared `src` package after
    # Worker tests have loaded another package with the same name.
    response = httpx.get(f"{os.environ['API_URL']}/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    for path in ("/v1/transcriptions", "/v1/diarizations"):
        encoding = schema["paths"][path]["post"]["requestBody"]["content"][
            "multipart/form-data"
        ]["encoding"]["hotwords"]

        assert encoding == {"style": "form", "explode": True}
