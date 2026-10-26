# syntax=docker/dockerfile:1.7
# Standart teg — dev uchun; prod build'da deploy/images.lock.env dagi digest beriladi (scripts/build_images.sh).
ARG PYTHON_IMAGE=python:3.12-slim-bookworm
# ── 1-bosqich: bog'liqliklar ────────────────────────────────────────
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
WORKDIR /build
COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN python -m venv /opt/venv \
 && if [ "$INSTALL_DEV" = "true" ]; then REQ=requirements-dev.txt; else REQ=requirements.txt; fi \
 && /opt/venv/bin/pip install --no-cache-dir --require-hashes --no-deps -r "$REQ"

# ── 2-bosqich: ishchi image ─────────────────────────────────────────
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
# Korporativ TLS-inspeksiya CA'sini RUNTIME image'ga ishonchli deb belgilash ixtiyoriy
# (build-arg, sukut bo'yicha `false`) — bugun (10.0.90.52) 1C oddiy HTTP orqali ishlaydi,
# runtime'da tashqi HTTPS integratsiyasi yo'q. Faqat shunday integratsiya kerak bo'lganda
# `--build-arg RUNTIME_EXTRA_CA=true` bilan yoqiladi (backend/certs/README.md'ga qarang).
ARG RUNTIME_EXTRA_CA=false
COPY certs/ /usr/local/share/ca-certificates/
# Avval korporativ CA yoqiladi (apt HTTPS, proksi orqali) va base digest'idan keyingi xavfsizlik
# tuzatishlari o'rnatiladi (Trivy HIGH); so'ng CA `RUNTIME_EXTRA_CA!=true` bo'lsa to'plamdan olib tashlanadi.
RUN update-ca-certificates \
 && sed -i 's|http://deb.debian.org|https://deb.debian.org|' /etc/apt/sources.list.d/debian.sources \
 && apt-get -o APT::Update::Error-Mode=any update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && if [ "$RUNTIME_EXTRA_CA" != "true" ]; then \
      find /usr/local/share/ca-certificates/ -name '*.crt' -delete; \
    fi \
 && update-ca-certificates --fresh \
 && groupadd --gid 10001 ugk \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin ugk
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
# Kod root'ga tegishli: ilova foydalanuvchisi uni o'zgartira olmaydi.
COPY app/ /app/app/
COPY migrations/ /app/migrations/
COPY alembic.ini pyproject.toml /app/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/healthz', timeout=3)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header", "--no-access-log"]
