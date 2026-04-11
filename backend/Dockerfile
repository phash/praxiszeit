# F-061: base image pinned to a specific patch release (not :3.12 or
# :3.12-slim). Bumping happens deliberately via Renovate/Dependabot, not
# via `docker pull`. Matched digest from Docker Hub:
#   python:3.12.7-slim-bookworm
#   sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
#
# F-038: Multi-stage build.
#
# Stage 1 (builder): full python-slim + gcc to compile native wheels for
# bcrypt, psycopg2-binary etc. into /wheels.
#
# Stage 2 (runtime): python-slim without gcc — installs the prebuilt wheels
# via --no-index so the final image has no C compiler and no build
# toolchain. Shrinks the attack surface and the image size (~200MB saved).
#
# psycopg2-binary ships its own libpq so runtime does NOT need
# postgresql-client. It was only needed at build time for compiling
# psycopg2 from source (not done since we use -binary).

FROM python:3.12.7-slim-bookworm AS builder

WORKDIR /build

# Build-time dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Produce wheels into /wheels so the runtime stage can install without
# network access or a compiler.
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────
FROM python:3.12.7-slim-bookworm AS runtime

WORKDIR /app

# Runtime system dependencies — only libpq5 for psycopg2 network support.
# No gcc, no postgresql-client binaries, no build toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install the prebuilt wheels (no index → no network fetch)
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Copy application code
COPY . .

# Create non-root user and set ownership
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && chown -R appuser:appuser /app
USER appuser

# Run migrations and start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='172.16.0.0/12,10.0.0.0/8,192.168.0.0/16'"]
