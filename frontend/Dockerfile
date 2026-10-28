# syntax=docker/dockerfile:1.7
# Standart teglar — dev uchun; prod build'da deploy/images.lock.env dagi digest'lar beriladi.
ARG NODE_IMAGE=node:22-alpine
ARG CADDY_IMAGE=caddy:2-alpine
ARG CADDY_BUILDER_IMAGE=caddy:builder-alpine
# Frontend: Node'da build (lockfile bo'yicha) → Caddy image'ga faqat statik fayllar.

# ── 1-bosqich: build ──────────────────────────────────────────────
# hadolint ignore=DL3006
FROM ${NODE_IMAGE} AS build
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

# ── 2-bosqich: Caddy'ni yangi Go va x/net bilan qayta yig'ish ────
# Rasmiy image'dagi caddy eski Go/x/net bilan yig'ilgan (Trivy HIGH); versiya qotirilgan image'dan olinadi.
# `--replace x/net` — upstream tuzatilgan caddy chiqarguncha (qayta ko'rish: scripts/pin_images.sh);
# bu istisno emas, tuzatish. Go modullari yaxlitligi GOSUMDB (sum.golang.org) orqali; repo ichida hash-lock yo'q.
# hadolint ignore=DL3006
FROM ${CADDY_IMAGE} AS caddy-stock
# hadolint ignore=DL3006
FROM ${CADDY_BUILDER_IMAGE} AS caddy-build
COPY --from=caddy-stock /usr/bin/caddy /tmp/caddy-stock
RUN --mount=type=bind,source=certs,target=/certs \
    if ls /certs/*.crt >/dev/null 2>&1; then \
      cat /etc/ssl/certs/ca-certificates.crt /certs/*.crt > /tmp/ca.pem; \
    else cp /etc/ssl/certs/ca-certificates.crt /tmp/ca.pem; fi
ENV SSL_CERT_FILE=/tmp/ca.pem GOFLAGS=-trimpath
RUN v="$(/tmp/caddy-stock version)" \
 && xcaddy build "${v%% *}" \
      --replace golang.org/x/net=golang.org/x/net@v0.60.0 \
      --replace github.com/go-jose/go-jose/v4=github.com/go-jose/go-jose/v4@v4.1.6 --output /caddy \
 && /caddy version \
 && cat /caddy > /caddy-nocap && chmod 0755 /caddy-nocap

# ── 3-bosqich: statik fayllar Caddy bilan ────────────────────────
# hadolint ignore=DL3006
FROM ${CADDY_IMAGE} AS web
# Korporativ CA faqat `apk upgrade` vaqtida ishonchli va faqat bind-mount orqali (qatlamga tushmaydi).
RUN --mount=type=bind,source=certs,target=/tmp/certs \
    cp /etc/ssl/certs/ca-certificates.crt /tmp/ca-bundle.orig \
 && if ls /tmp/certs/*.crt >/dev/null 2>&1; then cat /tmp/certs/*.crt >> /etc/ssl/certs/ca-certificates.crt; fi \
 && apk upgrade --no-cache \
 && cp /tmp/ca-bundle.orig /etc/ssl/certs/ca-certificates.crt \
 && rm -rf /tmp/ca-bundle.orig /usr/bin/caddy
# Binar yangi fayl sifatida yoziladi (cap_net_bind_service ko'chmaydi): 8080/8443 portlar, `cap_drop: ALL` bilan mos.
COPY --from=caddy-build /caddy-nocap /usr/bin/caddy
COPY --from=build /app/dist /srv
