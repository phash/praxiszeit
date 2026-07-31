# Build stage
# node:22-alpine — Node 20 ist seit 2026-04-30 EOL (keine Security-Patches mehr);
# 22 ist Active LTS. Nur Build-Stage (Runtime-Image ist nginx:alpine).
FROM node:22-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies — npm ci (deterministisch, lock-treu): scheitert hart bei
# package.json/lock-Drift statt still eine abweichende Auflösung zu bauen.
RUN npm ci

# Copy source code
COPY . .

# Build application
RUN npm run build

# Production stage
# Pinned to a specific version (Projektregel, Paritaet zu backend/Dockerfile's
# python:3.12.13-slim-bookworm-Pin) statt des floatenden `:alpine`-Tags, das
# sich ohne Vorwarnung unter dem Build aendern kann. Aktueller Stand (siehe
# `docker pull nginx:alpine` zum Zeitpunkt des Pins):
#   nginx:1.31.3-alpine
#   sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752
# Zum Aktualisieren bewusst per `docker pull nginx:alpine` + `docker inspect
# nginx:alpine --format '{{index .RepoDigests 0}}'` die neue Version+Digest
# holen, hier eintragen und den Frontend-Build (`docker compose build
# frontend`) + einen Smoke-Test (Login) verifizieren — nicht automatisch via
# Renovate/Dependabot ohne Review (gleiche Regel wie beim Backend-Image).
FROM nginx:1.31.3-alpine

# Copy built files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
