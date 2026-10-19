# syntax=docker/dockerfile:1.7
# Frontend: Node'da build (lockfile bo'yicha) → Caddy image'ga faqat statik fayllar.

# ── 1-bosqich: build ──────────────────────────────────────────────
FROM node:22-alpine AS build
WORKDIR /app
# Korporativ TLS proksi (ixtiyoriy): certs/*.crt bo'lmasa bo'sh fayl — Node faqat ogohlantiradi.
COPY certs/ /certs/
RUN cat /certs/*.crt > /tmp/extra-ca.pem 2>/dev/null || true
ENV NODE_EXTRA_CA_CERTS=/tmp/extra-ca.pem \
    npm_config_fund=false \
    npm_config_audit=false \
    npm_config_update_notifier=false
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

# ── 2-bosqich: statik fayllar Caddy bilan ────────────────────────
FROM caddy:2-alpine AS web
COPY --from=build /app/dist /srv
