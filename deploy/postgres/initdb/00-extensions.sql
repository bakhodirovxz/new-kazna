-- pg_stat_statements (spec 6.3). Superuser kerak — shu sabab initdb'da, Alembic migratsiyasida emas.
-- Mavjud klasterda bir marta:
--   docker compose -f deploy/compose.prod.yml ... exec db psql -U postgres -d ugekazna \
--     -f /docker-entrypoint-initdb.d/00-extensions.sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
