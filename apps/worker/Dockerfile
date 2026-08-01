FROM denoland/deno:2.3.0 AS deno

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    python3 \
    python3-pip \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deno /usr/bin/deno /usr/local/bin/deno

WORKDIR /app

COPY apps/worker/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --pre -r requirements.txt

COPY apps/worker/src ./src
COPY scripts/prepare-diarization-model.py scripts/smoke-diarization-model.py ./scripts/

CMD ["python3", "-m", "src.main"]
