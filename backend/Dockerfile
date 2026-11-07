# F-061 / Audit 2026-11-07 S3-05: base image pinned to a patch release AND
# its manifest-list digest (multi-arch index), so `docker build --pull` gets
# exactly this image and a re-tagged upstream image never enters the build
# unnoticed. Bumping (also for Debian security updates of the same tag) is a
# deliberate change of BOTH stages below:
#   docker buildx imagetools inspect python:3.12.16-slim-bookworm | sed -n 's/^Digest: *//p'
# Digest as of 2026-11-07:
#   sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
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

FROM python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS builder

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
FROM python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime

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

# Run migrations, set up the read-only backup role, start uvicorn WITHOUT the
# superuser URL (docker-start.sh, Audit 2026-11-07 S3-13).
CMD ["sh", "/app/docker-start.sh"]
