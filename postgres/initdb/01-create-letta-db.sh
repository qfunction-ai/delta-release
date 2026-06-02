#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'letta') THEN
            CREATE DATABASE letta;
        END IF;
    END
    \$\$;
    GRANT ALL PRIVILEGES ON DATABASE letta TO $POSTGRES_USER;
EOSQL
