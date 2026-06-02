#!/bin/bash
set -e
# Create the letta database if it doesn't already exist.
# CREATE DATABASE cannot be run inside a transaction (DO block), and
# IF NOT EXISTS is not supported for CREATE DATABASE in PostgreSQL.
# createdb is a wrapper that exits 0 on success, non-zero if the
# database already exists — the || true handles the idempotent case.
createdb --username "$POSTGRES_USER" --echo letta 2>&1 || true
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    GRANT ALL PRIVILEGES ON DATABASE letta TO $POSTGRES_USER;
EOSQL
