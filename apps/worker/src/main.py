import logging
import time

from .config import load_settings
from .dependencies import production_dependencies
from .processor import process_job
from .repository import claim_next_job
from .model_registry import validate_pinned_model
from .device import log_inference_devices, resolve_inference_devices


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.model_root.mkdir(parents=True, exist_ok=True)
    validate_pinned_model(settings)
    devices = resolve_inference_devices(settings.inference_device)
    log_inference_devices(devices)
    dependencies = production_dependencies(settings, devices)
    logging.info("worker %s started", settings.worker_id)
    while True:
        job = claim_next_job(settings)
        if job is None:
            time.sleep(settings.poll_interval_seconds)
            continue
        logging.info("processing job %s", job["id"])
        process_job(settings, dependencies, job)


if __name__ == "__main__":
    main()
