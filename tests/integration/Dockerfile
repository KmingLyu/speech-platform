FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY apps/api-server/requirements.txt /tmp/api-requirements.txt
COPY tests/integration/requirements.txt /tmp/test-requirements.txt
RUN pip install --no-cache-dir \
    -r /tmp/api-requirements.txt \
    -r /tmp/test-requirements.txt

COPY apps ./apps
COPY tests ./tests

CMD ["sh", "-c", "python -m mypy --ignore-missing-imports apps/api-server/src && python -m mypy --ignore-missing-imports apps/worker/src && pytest -q tests/integration"]
