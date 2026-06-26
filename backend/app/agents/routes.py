import json
import logging

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.agents.schemas import AgentCreate, AgentResponse, AgentUpdate, EmbeddingModelResponse, ModelResponse
from app.agents.tools import attach_file_tools
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.constants import DEFAULT_PERSONA, OLLAMA_DISCOVERY_URLS
from app.database import get_db, get_owned_or_404, list_owned
from app.letta_client import call_letta, get_letta_client

router = APIRouter(prefix="/api/agents", tags=["agents"])

logger = logging.getLogger(__name__)

# Known embedding models with their dimensions
KNOWN_EMBEDDING_MODELS = [
    {"id": "letta/letta-free", "name": "letta-free", "provider": "letta", "dimensions": 1536},
    {"id": "openai/text-embedding-ada-002", "name": "text-embedding-ada-002", "provider": "openai", "dimensions": 1536},
    {"id": "openai/text-embedding-3-small", "name": "text-embedding-3-small", "provider": "openai", "dimensions": 1536},
    {"id": "openai/text-embedding-3-large", "name": "text-embedding-3-large", "provider": "openai", "dimensions": 3072},
]

DEFAULT_EMBEDDING = "letta/letta-free"


async def _discover_ollama_models() -> tuple[list[dict], str | None]:
    """Query Ollama for available models. Returns (models, base_url).

    Tries each discovery URL in order, returns models from the first
    that responds. Returns ([], None) if all URLs fail.
    """
    for ollama_url in OLLAMA_DISCOVERY_URLS:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(ollama_url)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("models", []), ollama_url
        except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException):
            continue
    return [], None


def _derive_provider_type(model: str) -> str:
    """Derive provider_type from the model handle string.

    Letta requires provider_type to know which API to call.
    Valid values: openai, ollama, anthropic, google_ai, google_vertex, azure, groq, xai, zai, sglang.
    Ollama uses the OpenAI-compatible API but has its own provider_type for correct
    defaults (e.g. strict=false, prompt-based tool calling fallback).
    """
    model_lower = model.lower()
    if model_lower.startswith("anthropic/"):
        return "anthropic"
    if model_lower.startswith("google_ai/"):
        return "google_ai"
    if model_lower.startswith("google_vertex/"):
        return "google_vertex"
    if model_lower.startswith("azure/"):
        return "azure"
    if model_lower.startswith("groq/"):
        return "groq"
    if model_lower.startswith("xai/"):
        return "xai"
    if model_lower.startswith("ollama/"):
        return "ollama"
    # letta/, openai/, local/, and unknown all use the OpenAI-compatible API
    return "openai"


@router.get("/models", response_model=list[ModelResponse])
async def list_models(
    current_user: User = Depends(get_current_user),
):
    """List available LLM models from Letta plus any discovered from Ollama."""
    client = get_letta_client()
    models = await call_letta(client.models.list)
    result = [
        ModelResponse(id=m.handle, name=m.display_name or m.name, provider=m.provider_name or "unknown") for m in models
    ]

    # Discover LLM models from Ollama (exclude embedding models)
    seen_handles = {m.id for m in result}
    ollama_models, _ = await _discover_ollama_models()
    for model in ollama_models:
        name = model.get("name", "")
        handle = f"ollama/{name}"
        # Skip embedding models and already-known handles
        if "embed" in name.lower() or handle in seen_handles:
            continue
        result.append(ModelResponse(id=handle, name=name, provider="ollama"))
        seen_handles.add(handle)

    return result


@router.get("/embedding-models", response_model=list[EmbeddingModelResponse])
async def list_embedding_models(
    current_user: User = Depends(get_current_user),
):
    """List available embedding models.

    Returns known embedding models plus any discovered from Ollama if configured.
    """
    models = [EmbeddingModelResponse(**m) for m in KNOWN_EMBEDDING_MODELS]

    # Try to discover embedding models from Ollama
    ollama_models, ollama_url = await _discover_ollama_models()
    if ollama_url:
        show_url = ollama_url.replace("/api/tags", "/api/show")
        async with httpx.AsyncClient(timeout=5.0) as client:
            for model in ollama_models:
                name = model.get("name", "")
                # Only include embedding models (name contains "embed")
                if "embed" in name.lower():
                    # Try to get embedding dimensions from model details
                    dimensions = None
                    try:
                        show_resp = await client.post(show_url, json={"name": name})
                        if show_resp.status_code == 200:
                            info = show_resp.json()
                            model_info = info.get("model_info", {})
                            for key, val in model_info.items():
                                if "embedding_length" in key or "embedding_dim" in key:
                                    dimensions = int(val)
                                    break
                    except (httpx.HTTPError, httpx.ConnectError, json.JSONDecodeError, KeyError):
                        pass
                    models.append(
                        EmbeddingModelResponse(
                            id=f"ollama/{name}",
                            name=name,
                            provider="ollama",
                            dimensions=dimensions,
                        )
                    )

    return models


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's agents."""
    return await list_owned(db, Agent, current_user.id)


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent."""
    client = get_letta_client()

    # Use specified embedding model or default
    embedding_model = agent_data.embedding_model or DEFAULT_EMBEDDING

    from app.credentials.service import build_credential_secrets_dict

    secrets = await build_credential_secrets_dict(current_user.id, db)

    letta_agent = await call_letta(
        client.agents.create,
        name=agent_data.name,
        model=agent_data.model,
        embedding=embedding_model,
        memory_blocks=[
            {"label": "persona", "value": DEFAULT_PERSONA},
            {"label": "human", "value": f"Operator: {current_user.username}"},
            {"label": "workflow_context", "value": ""},
            {"label": "findings", "value": "[]"},
        ],
        include_base_tools=True,
        model_settings={"provider_type": _derive_provider_type(agent_data.model), "temperature": 0.0},
        secrets=secrets,
    )

    # Attach file persistence tools (file_list, file_read, file_write, grep_files)
    await attach_file_tools(client, letta_agent.id)

    # Store reference in database
    agent = Agent(
        user_id=current_user.id,
        letta_agent_id=letta_agent.id,
        name=agent_data.name,
        model=agent_data.model,
        embedding=embedding_model,
    )
    db.add(agent)
    await db.flush()

    return agent


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get agent details."""
    agent = await get_owned_or_404(db, Agent, agent_id, current_user.id)

    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    agent_data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent (name only)."""
    agent = await get_owned_or_404(db, Agent, agent_id, current_user.id)

    if agent_data.name is not None:
        # Update name in Letta first — if it fails, don't change DB either
        client = get_letta_client()
        await call_letta(client.agents.update, agent.letta_agent_id, name=agent_data.name)
        agent.name = agent_data.name

    await db.flush()
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent."""
    agent = await get_owned_or_404(db, Agent, agent_id, current_user.id)

    client = get_letta_client()
    await call_letta(client.agents.delete, agent.letta_agent_id, raise_on_error=False)

    await db.delete(agent)
