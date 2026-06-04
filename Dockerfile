# NIFTY Options Buyer - Docker image
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY src/ ./src/
COPY config/ ./config/
COPY tests/ ./tests/
COPY .env.example .env.example

ENV PYTHONUNBUFFERED=1 \
    APP_MODE=mock \
    LOG_LEVEL=INFO

EXPOSE 8050

# Default: run dashboard
CMD ["python", "-m", "main", "dashboard", "--host", "0.0.0.0", "--port", "8050"]
