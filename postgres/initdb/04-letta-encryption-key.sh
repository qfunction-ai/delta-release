#!/bin/bash
# 04-letta-encryption-key.sh — generate the Letta secrets-encryption key (F4/Q-5).
#
# Runs on fresh volume init only, alongside 03-letta-role.sh. The key is
# written to the letta_secrets volume; the letta command wrapper exports
# it as LETTA_ENCRYPTION_KEY so agent secrets are encrypted at rest from
# the first write (the fork's Secret.from_plaintext falls back to
# plaintext when the key is unset).
#
# chmod 640: same setgid-group arrangement as letta_pg_password (see
# 03-letta-role.sh).
set -e

mkdir -p /letta-secrets
if [ -s /letta-secrets/letta_encryption_key ]; then
    echo "letta encryption key already exists — keeping it"
    exit 0
fi

head -c 32 /dev/urandom | base64 > /letta-secrets/letta_encryption_key
chmod 640 /letta-secrets/letta_encryption_key
echo "letta encryption key written to /letta-secrets/letta_encryption_key"
