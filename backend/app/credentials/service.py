"""Credential business logic — decoupled from routes for cross-module reuse."""

import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.async_utils import run_sync
from app.constants import LETTA_DB_ERRORS
from app.credentials.encryption import decrypt_value
from app.credentials.models import Credential
from app.letta_client import get_letta_client

logger = logging.getLogger(__name__)


def _credential_to_env_var(cred: Credential) -> tuple[str, str]:
    """Decrypt a credential and build the CREDENTIAL_<key> env var pair.

    Returns (env_var_name, json_value) where json_value contains
    primary_key, secondary_key, and url fields.
    """
    value = json.dumps(
        {
            "primary_key": decrypt_value(cred.primary_key_encrypted),
            "secondary_key": decrypt_value(cred.secondary_key_encrypted) if cred.secondary_key_encrypted else None,
            "url": cred.url,
        }
    )
    return f"CREDENTIAL_{cred.key}", value


async def build_credential_secrets_dict(user_id: str, db: AsyncSession) -> dict[str, str]:
    """Build a dict of CREDENTIAL_<key> → JSON value for all of a user's credentials.

    Extracted from routes so that agents/routes.py can call it without
    importing from the credentials routes layer.
    """
    result = await db.execute(select(Credential).where(Credential.user_id == user_id))
    credentials = result.scalars().all()

    secrets = {}
    for cred in credentials:
        key, value = _credential_to_env_var(cred)
        secrets[key] = value

    return secrets


async def sync_credential_secrets(user_id: str, db: AsyncSession) -> dict[str, str]:
    """Sync all credentials for a user to all of their agents as Letta secrets.

    Credential values are stored as JSON strings under CREDENTIAL_<key> env vars,
    containing primary_key, secondary_key, and url fields. Tools access them via
    os.getenv("CREDENTIAL_<key>").

    Because Letta's agents.update(secrets={...}) replaces all secrets (not merges),
    we must read-merge-write: fetch current secrets, replace CREDENTIAL_ entries,
    and write back the full set.

    Returns a dict of agent_id → "ok"|"failed" for each agent synced.
    """
    # Get all user's credentials (encrypted — we decrypt per-agent to minimize
    # time plaintext is in memory)
    result = await db.execute(select(Credential).where(Credential.user_id == user_id))
    credentials = result.scalars().all()

    result = await db.execute(select(Agent).where(Agent.user_id == user_id))
    agents = result.scalars().all()

    if not agents:
        return {}

    client = get_letta_client()

    # Bounded concurrency — limit parallel Letta API calls to avoid overwhelming it
    semaphore = asyncio.Semaphore(5)
    results: dict[str, str] = {}

    async def _sync_one_agent(agent):
        async with semaphore:
            # Decrypt credentials per-agent to minimize time plaintext is in memory.
            # Build the secrets dict fresh for each agent so we can clear it
            # immediately after the API call.
            cred_secrets = {}
            for cred in credentials:
                key, value = _credential_to_env_var(cred)
                cred_secrets[key] = value

            try:
                letta_agent = await run_sync(client.agents.retrieve, agent.letta_agent_id)

                # Preserve non-credential secrets
                current_secrets = {}
                if letta_agent.tool_exec_environment_variables:
                    for env_var in letta_agent.tool_exec_environment_variables:
                        if not env_var.key.startswith("CREDENTIAL_"):
                            current_secrets[env_var.key] = env_var.value

                # Merge credential secrets
                merged = {**current_secrets, **cred_secrets}

                await run_sync(
                    client.agents.update,
                    agent_id=agent.letta_agent_id,
                    secrets=merged,
                )
                results[agent.letta_agent_id] = "ok"
            except LETTA_DB_ERRORS as e:
                logger.warning("Failed to sync secrets to agent %s: %s", agent.letta_agent_id, e)
                results[agent.letta_agent_id] = "failed"
            finally:
                # Clear decrypted secrets from memory immediately after use
                del cred_secrets

    await asyncio.gather(*[_sync_one_agent(agent) for agent in agents])
    return results
