# syntax=docker/dockerfile:1
FROM python:3.12-slim

# ── System dependencies ────────────────────────────────────────────────────────
# ffmpeg: for merging video+audio streams
# Playwright Chromium dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    wget \
    gnupg \
    # Chromium system deps
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    fonts-liberation \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Install Playwright + Chromium browser ─────────────────────────────────────
# Use `python -m playwright` (reliable in Docker; bare `playwright` may not be on PATH)
# --with-deps is omitted because system deps are already installed above
RUN python -m playwright install chromium

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# Koyeb injects PORT env var; fall back to 8000 for local testing
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE ${PORT}

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
