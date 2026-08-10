FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.lock pyproject.toml README.md ./
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY apps ./apps
COPY packages ./packages
COPY collectors ./collectors
COPY config ./config
COPY db ./db
COPY alembic.ini ./
RUN python -m pip install --no-cache-dir --no-deps .

EXPOSE 8000

CMD ["uvicorn", "signal_observatory_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
