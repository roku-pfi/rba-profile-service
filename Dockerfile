# Build from the polyrepo root (develop/):
#   docker build -f rba-profile-service/Dockerfile -t rba-profile-service:dev .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --no-cache-dir -U pip setuptools wheel

COPY rba-features /opt/rba-features
COPY rba-contracts /opt/rba-contracts
COPY rba-profile-service /app

RUN pip install --no-cache-dir /opt/rba-features /opt/rba-contracts /app \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser
CMD ["rba-profile-service"]
