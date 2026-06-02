#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "letta" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
