# F-061: base image pinned to a specific patch release (not :3.12 or
# :3.12-slim). Bumping happens deliberately via Renovate/Dependabot, not
# via `docker pull`. Matched digest from Docker Hub:
#   python:3.12.13-slim-bookworm
#   sha256:58525e1a8dada8e72d6f8a11a0ddff8d981fd888549108db52455d577f927f77
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

FROM python:3.12.13-slim-bookworm AS builder

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
FROM python:3.12.13-slim-bookworm AS runtime

WORKDIR /app

# Runtime system dependencies: libpq5 (psycopg2) + postgresql-client-18 for the
# #213 DB-Backup-Feature (pg_dump). Der Client MUSS zur Server-Major (postgres:18)
# passen — bookworm liefert nur Client 15 (verweigert den Dump eines 18er-Servers),
# daher das PGDG-Repo. curl/gnupg werden nur fuer den Repo-Key gebraucht und danach
# wieder entfernt.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl ca-certificates gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-18 \
    && apt-get purge -y curl gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install the prebuilt wheels (no index → no network fetch)
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Copy application code
COPY . .

# Create non-root user and set ownership.
# #213: /app/backups vorab anlegen + dem appuser geben — beim ersten Mount eines
# (leeren) named volumes uebernimmt Docker die Ownership dieses Image-Pfads, sonst
# gehoert der Mountpoint root und der non-root-Backend kann pg_dump nicht schreiben.
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /app/backups \
    && chown -R appuser:appuser /app
USER appuser

# Run migrations and start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='172.16.0.0/12,10.0.0.0/8,192.168.0.0/16'"]
