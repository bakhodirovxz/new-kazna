# syntax=docker/dockerfile:1.7
# UGEKAZNA DB image: PostgreSQL 16 + pgBackRest + prod konfiguratsiyasi (spec 2, 6.3, 11).
# Build konteksti — deploy/ (deploy/.dockerignore faqat postgres/ va pgbackrest/ ni o'tkazadi):
#   docker build -f deploy/postgres/Dockerfile --build-arg POSTGRES_IMAGE=... -t ugekazna-db:<v> deploy
ARG POSTGRES_IMAGE=postgres:16-alpine
# hadolint ignore=DL3006
FROM ${POSTGRES_IMAGE}

# Korporativ CA faqat `apk add` vaqtida ishonchli va faqat bind-mount orqali (qatlamga tushmaydi);
# oxirgi image'da asl to'plam tiklanadi.
# `postgresql` virtual paketi: pgbackrest `postgresql` ga bog'liq, lekin server bizda PG16 (/usr/local);
# virtual paket PG18 serverini (postgresql18, postgresql18-client) tortishni oldini oladi (faqat libpq
# kutubxonasi o'rnatiladi; ish vaqtida /usr/local/lib dagi PG16 libpq yuklanadi). SBOM'dagi
# `postgresql` (noarch, sana versiyali) — shu virtual paket, PG16 emas: PG16 `pkg:generic/postgresql` bilan.
# gosu o'chiriladi: image USER 70:70 ostida ishlaydi (root yo'q), gosu ishlatilmaydi; uning Go stdlib'i eski (Trivy).
RUN --mount=type=bind,source=postgres/certs,target=/tmp/certs \
    cp /etc/ssl/certs/ca-certificates.crt /tmp/ca-bundle.orig \
 && if ls /tmp/certs/*.crt >/dev/null 2>&1; then cat /tmp/certs/*.crt >> /etc/ssl/certs/ca-certificates.crt; fi \
 && apk add --no-cache --virtual postgresql musl \
 && apk add --no-cache pgbackrest jq \
 && cp /tmp/ca-bundle.orig /etc/ssl/certs/ca-certificates.crt \
 && rm -f /tmp/ca-bundle.orig /usr/local/bin/gosu \
 && install -d -o postgres -g postgres -m 0750 /var/lib/pgbackrest \
 && install -d -m 0755 /etc/pgbackrest /etc/postgresql/profiles

COPY postgres/postgresql.conf postgres/pg_hba.conf /etc/postgresql/
COPY postgres/profiles/ /etc/postgresql/profiles/
COPY postgres/initdb/ /docker-entrypoint-initdb.d/
COPY pgbackrest/pgbackrest.conf /etc/pgbackrest/pgbackrest.conf
COPY --chmod=0755 postgres/bin/ugk-db-entrypoint pgbackrest/bin/ugk-pgbackrest-env \
     pgbackrest/bin/ugk-backup pgbackrest/bin/ugk-restore /usr/local/bin/

ENV PGBACKREST_CONFIG_INCLUDE_PATH=/tmp/pgbackrest/conf.d
USER 70:70
ENTRYPOINT ["ugk-db-entrypoint"]
CMD ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
