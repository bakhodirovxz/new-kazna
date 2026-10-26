# syntax=docker/dockerfile:1.7
# UGEKAZNA DB image: PostgreSQL 16 + pgBackRest + prod konfiguratsiyasi (spec 2, 6.3, 11).
# Build konteksti — deploy/ (deploy/.dockerignore faqat postgres/ va pgbackrest/ ni o'tkazadi):
#   docker build -f deploy/postgres/Dockerfile --build-arg POSTGRES_IMAGE=... -t ugekazna-db:<v> deploy
ARG POSTGRES_IMAGE=postgres:16-alpine
FROM ${POSTGRES_IMAGE}

COPY postgres/certs/ /tmp/certs/
RUN if ls /tmp/certs/*.crt >/dev/null 2>&1; then cat /tmp/certs/*.crt >> /etc/ssl/certs/ca-certificates.crt; fi \
 && apk add --no-cache pgbackrest jq \
 && rm -rf /tmp/certs \
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
