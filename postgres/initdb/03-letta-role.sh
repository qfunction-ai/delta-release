#!/bin/bash
# 03-letta-role.sh — create the scoped `letta` Postgres role (F4).
#
# Runs on fresh postgres_data volume init only, after 01 creates the
# `letta` database and 02 enables pgvector (both need the superuser).
#
# The generated password lands on the letta_secrets volume, which the
# letta container mounts at /data/letta-secrets: its command wrapper
# reads it and overrides LETTA_PG_URI, so the letta server connects as
# the scoped role instead of the superuser.
#
# chmod 640: init-volumes pre-creates these files 999:1000 640 (setgid on
# the volume root does not survive Docker Desktop's mount layer), and
# redirection into a pre-owned file preserves ownership — so postgres
# (UID 999) writes and the letta wrapper (UID 1000) reads via the group.
# The volume is mounted nowhere else and is not on any Landlock read path.
set -e

# Idempotency: skip if the role already exists (volume re-init scenarios).
ROLE_EXISTS=$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname='letta'")
if [ "$ROLE_EXISTS" = "1" ]; then
    echo "letta role already exists — skipping creation"
    exit 0
fi

# Alphanumeric-only password (43 chars ≈ 256 bits): URL-safe by
# construction, so the wrapper can drop it into LETTA_PG_URI verbatim
# (no URL-encoding step — which previously required python3, not
# present in the pgvector image).
PG_PASSWORD=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 43)

mkdir -p /letta-secrets
printf '%s' "$PG_PASSWORD" > /letta-secrets/letta_pg_password
chmod 640 /letta-secrets/letta_pg_password

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE letta LOGIN PASSWORD '${PG_PASSWORD}';
    ALTER DATABASE letta OWNER TO letta;
    REVOKE CONNECT ON DATABASE delta FROM PUBLIC;
    GRANT CONNECT ON DATABASE delta TO delta;
EOSQL

echo "letta role created; password written to /letta-secrets/letta_pg_password"
