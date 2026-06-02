from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas import BaseORMSchema


class AgentCreate(BaseModel):
    name: str
    model: str
    embedding_model: str | None = None  # Optional, defaults to letta/letta-free


class AgentUpdate(BaseModel):
    name: str | None = None


class AgentResponse(BaseORMSchema):
    id: UUID
    user_id: UUID
    letta_agent_id: str
    name: str
    model: str
    embedding: str
    created_at: datetime


class ModelResponse(BaseModel):
    id: str
    name: str
    provider: str


class EmbeddingModelResponse(BaseModel):
    id: str
    name: str
    provider: str
    dimensions: int | None = None
