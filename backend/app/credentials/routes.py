import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.credentials.encryption import encrypt_value
from app.credentials.models import Credential
from app.credentials.schemas import (
    CREDENTIAL_TYPES,
    PROVIDERS,
    CredentialCreate,
    CredentialResponse,
    CredentialTypeResponse,
    CredentialUpdate,
    ProviderResponse,
)
from app.credentials.service import sync_credential_secrets
from app.database import check_unique_for_user, get_db, get_owned_or_404, list_owned
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    current_user: User = Depends(get_current_user),
):
    """List supported credential providers."""
    return [
        ProviderResponse(
            id=key,
            display_name=info["display_name"],
            requires_url=info["requires_url"],
            requires_secret=info["requires_secret"],
            url_placeholder=info.get("url_placeholder"),
        )
        for key, info in PROVIDERS.items()
    ]


@router.get("/types", response_model=list[CredentialTypeResponse])
async def list_credential_types(
    current_user: User = Depends(get_current_user),
):
    """List supported credential types."""
    return [
        CredentialTypeResponse(
            id=key,
            display_name=info["display_name"],
            fields=info["fields"],
        )
        for key, info in CREDENTIAL_TYPES.items()
    ]


@router.get("/", response_model=list[CredentialResponse])
async def list_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's credentials (without revealing secret values)."""
    credentials = await list_owned(db, Credential, current_user.id)

    return [CredentialResponse.from_credential(c) for c in credentials]


@router.post("/", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_credential(
    request: Request,
    credential_data: CredentialCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new credential."""
    # Validate provider (accept both named providers and credential types)
    valid_providers = set(PROVIDERS.keys()) | set(CREDENTIAL_TYPES.keys())
    if credential_data.provider not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider: {credential_data.provider}"
        )

    if credential_data.provider in PROVIDERS:
        provider_info = PROVIDERS[credential_data.provider]
        if provider_info["requires_url"] and not credential_data.url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provider {credential_data.provider} requires url"
            )
        if provider_info["requires_secret"] and not credential_data.secondary_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider {credential_data.provider} requires secondary_key",
            )

    # Check for duplicate key (scoped per user)
    await check_unique_for_user(db, Credential, current_user.id, "key", credential_data.key, error_label="Credential")

    # Encrypt sensitive fields
    credential = Credential(
        user_id=current_user.id,
        key=credential_data.key,
        name=credential_data.name,
        provider=credential_data.provider,
        url=credential_data.url,
        primary_key_encrypted=encrypt_value(credential_data.primary_key),
        secondary_key_encrypted=encrypt_value(credential_data.secondary_key) if credential_data.secondary_key else None,
    )

    db.add(credential)
    await db.flush()

    # Sync credential secrets to all user's agents
    sync_results = await sync_credential_secrets(current_user.id, db)
    if sync_results:
        failed = [aid for aid, status in sync_results.items() if status == "failed"]
        if failed:
            logger.warning("Credential sync failed for %d agent(s): %s", len(failed), failed)

    return CredentialResponse.from_credential(credential)


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get credential details (without revealing secret values)."""
    credential = await get_owned_or_404(db, Credential, credential_id, current_user.id)

    return CredentialResponse.from_credential(credential)


@router.put("/{credential_id}", response_model=CredentialResponse)
@limiter.limit("5/minute")
async def update_credential(
    request: Request,
    credential_id: str,
    credential_data: CredentialUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a credential."""
    credential = await get_owned_or_404(db, Credential, credential_id, current_user.id)

    if credential_data.key is not None and credential_data.key != credential.key:
        await check_unique_for_user(
            db,
            Credential,
            current_user.id,
            "key",
            credential_data.key,
            exclude_id=credential.id,
            error_label="Credential",
        )
        credential.key = credential_data.key

    if credential_data.name is not None:
        credential.name = credential_data.name

    if credential_data.url is not None:
        credential.url = credential_data.url

    if credential_data.primary_key is not None:
        credential.primary_key_encrypted = encrypt_value(credential_data.primary_key)

    if credential_data.secondary_key is not None:
        credential.secondary_key_encrypted = encrypt_value(credential_data.secondary_key)

    await db.flush()

    # Sync credential secrets to all user's agents
    sync_results = await sync_credential_secrets(current_user.id, db)
    if sync_results:
        failed = [aid for aid, status in sync_results.items() if status == "failed"]
        if failed:
            logger.warning("Credential sync failed for %d agent(s): %s", len(failed), failed)

    return CredentialResponse.from_credential(credential)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def delete_credential(
    request: Request,
    credential_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a credential."""
    credential = await get_owned_or_404(db, Credential, credential_id, current_user.id)

    await db.delete(credential)
    await db.flush()  # Ensure deletion is visible before syncing secrets

    # Sync credential secrets to all user's agents (removes deleted credential)
    sync_results = await sync_credential_secrets(current_user.id, db)
    if sync_results:
        failed = [aid for aid, status in sync_results.items() if status == "failed"]
        if failed:
            logger.warning("Credential sync failed for %d agent(s): %s", len(failed), failed)
