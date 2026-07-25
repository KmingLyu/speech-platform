import os

import httpx

from harness import run_fake_worker


API_URL = os.environ["API_URL"]


def test_private_network_lifecycle_smoke() -> None:
    """Exercise the documented owner workflow without GPU or external network."""
    with httpx.Client(base_url=API_URL) as client:
        created = client.post(
            "/v1/transcriptions",
            data={"youtube_url": "https://youtu.be/smoke-retry", "formats": "txt"},
        )
        assert created.status_code == 202
        location = created.headers["Location"]
        job_id = created.json()["id"]

        listed = client.get("/v1/transcriptions?status=queued&limit=20")
        assert listed.status_code == 200
        assert job_id in {item["id"] for item in listed.json()["items"]}
        assert client.get(f"{location}?format=txt").status_code == 409

        run_fake_worker(
            env={"FAKE_SOURCE_FAILURE": "retryable", "MAX_ATTEMPTS": "1"},
            check=False,
        )
        # The fake worker reports the failure through the job state and exits
        # cleanly so the test container can continue with the manual retry.
        assert client.get(location).json()["status"] == "failed"

        retried = client.post(f"{location}/retry")
        assert retried.status_code == 202
        assert retried.json()["id"] == job_id
        run_fake_worker()
        assert client.get(location).json()["status"] == "completed"
        assert client.get(f"{location}?format=txt").text == "A deterministic transcript.\n"

        canceled = client.post(
            "/v1/transcriptions",
            data={"youtube_url": "https://youtu.be/smoke-cancel"},
        )
        canceled_location = canceled.headers["Location"]
        assert client.post(f"{canceled_location}/cancel").json()["status"] == "canceled"
        assert client.delete(canceled_location).status_code == 204
        assert client.delete(location).status_code == 204
