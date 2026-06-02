from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas import BaseORMSchema

# Unified credential schemas — single source of truth.
# Each entry defines a provider with its credential type and required fields.
# The CREDENTIAL_TYPES dict is derived from this, so there's no duplication.
CREDENTIAL_SCHEMAS = {
    # Security tool providers
    "splunk": {
        "display_name": "Splunk",
        "credential_type": "api_key_only",
        "fields": ["primary_key"],
        "requires_url": True,
        "requires_secondary_key": False,
        "url_placeholder": "https://your-splunk-instance.splunkcloud.com:8089",
    },
    "crowdstrike": {
        "display_name": "CrowdStrike",
        "credential_type": "api_key_pair",
        "fields": ["primary_key", "secondary_key"],
        "requires_url": True,
        "requires_secondary_key": True,
        "url_placeholder": "https://api.crowdstrike.com",
    },
    "sentinelone": {
        "display_name": "SentinelOne",
        "credential_type": "api_key_pair",
        "fields": ["primary_key", "secondary_key"],
        "requires_url": True,
        "requires_secondary_key": True,
        "url_placeholder": "https://your-instance.sentinelone.net",
    },
    "elastic": {
        "display_name": "Elastic Security",
        "credential_type": "api_key_only",
        "fields": ["primary_key"],
        "requires_url": True,
        "requires_secondary_key": False,
        "url_placeholder": "https://your-elasticsearch-instance:9200",
    },
    "custom": {
        "display_name": "Custom API",
        "credential_type": "api_key_pair",
        "fields": ["primary_key", "secondary_key"],
        "requires_url": True,
        "requires_secondary_key": True,
        "url_placeholder": "https://api.example.com",
    },
    # Generic types for custom integrations
    "api_key_only": {
        "display_name": "API Key (Single Token)",
        "credential_type": "api_key_only",
        "fields": ["primary_key"],
        "requires_url": True,
        "requires_secondary_key": False,
        "url_placeholder": "https://api.example.com",
    },
    "api_key_pair": {
        "display_name": "API Key Pair",
        "credential_type": "api_key_pair",
        "fields": ["primary_key", "secondary_key"],
        "requires_url": True,
        "requires_secondary_key": True,
        "url_placeholder": "https://api.example.com",
    },
    "basic_auth": {
        "display_name": "Username / Password",
        "credential_type": "basic_auth",
        "fields": ["primary_key", "secondary_key"],
        "requires_url": True,
        "requires_secondary_key": True,
        "url_placeholder": "https://api.example.com",
    },
}

# Credential types — derived from CREDENTIAL_SCHEMAS
CREDENTIAL_TYPES = {
    ctype: {
        "display_name": schema["display_name"],
        "fields": schema["fields"],
    }
    for ctype, schema in CREDENTIAL_SCHEMAS.items()
    if ctype in ("api_key_only", "api_key_pair", "basic_auth")
}

# Known credential providers — derived from CREDENTIAL_SCHEMAS
PROVIDERS = {
    k: {
        "display_name": v["display_name"],
        "requires_url": v["requires_url"],
        "requires_secret": v["requires_secondary_key"],
        "url_placeholder": v.get("url_placeholder"),
    }
    for k, v in CREDENTIAL_SCHEMAS.items()
    if k not in ("api_key_only", "api_key_pair", "basic_auth")
}


class CredentialCreate(BaseModel):
    key: str  # Unique identifier like SPLUNK_API_KEY
    name: str
    provider: str
    url: str | None = None
    primary_key: str
    secondary_key: str | None = None

    # NOTE: url is NOT validated at create-time for SSRF because the
    # resolved IP would be discarded (no column to store it). If a credential
    # test endpoint is re-added, SSRF validation with IP pinning must happen
    # at test-time in the same request — no TOCTOU window.


class CredentialUpdate(BaseModel):
    key: str | None = None
    name: str | None = None
    url: str | None = None
    primary_key: str | None = None
    secondary_key: str | None = None

    # NOTE: Same as CredentialCreate — SSRF validation with IP pinning
    # happens at test-time, not at update-time.


class CredentialResponse(BaseORMSchema):
    id: UUID
    user_id: UUID
    key: str
    name: str
    provider: str
    url: str | None
    has_secondary_key: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_credential(cls, credential) -> "CredentialResponse":
        """Construct from a Credential ORM object, computing has_secondary_key."""
        return cls(
            id=credential.id,
            user_id=credential.user_id,
            key=credential.key,
            name=credential.name,
            provider=credential.provider,
            url=credential.url,
            has_secondary_key=bool(credential.secondary_key_encrypted),
            created_at=credential.created_at,
            updated_at=credential.updated_at,
        )


class ProviderResponse(BaseModel):
    id: str
    display_name: str
    requires_url: bool
    requires_secret: bool
    url_placeholder: str | None


class CredentialTypeResponse(BaseModel):
    id: str
    display_name: str
    fields: list[str]
