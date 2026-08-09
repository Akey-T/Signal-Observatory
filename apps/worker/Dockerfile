FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.lock pyproject.toml README.md ./
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY apps ./apps
COPY packages ./packages
COPY config ./config
COPY db ./db
RUN python -m pip install --no-cache-dir --no-deps .

CMD ["python", "-m", "signal_observatory_worker.main"]
