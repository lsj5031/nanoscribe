# Builder stage
FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --compile-bytecode --no-cache -r requirements.txt

# Runtime stage
FROM python:3.13-alpine
ENV PYTHONUNBUFFERED=1
RUN apk add --no-cache ffmpeg
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY bot.py ./
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD pgrep -f "python bot.py" || exit 1
CMD ["python", "bot.py"]
