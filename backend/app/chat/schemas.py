from pydantic import BaseModel, field_validator


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    tool_ids: list[str] | None = None
    skill_ids: list[str] | None = None
    include_reasoning: bool = False

    @field_validator("skill_ids")
    @classmethod
    def max_one_skill(cls, v):
        if v is not None and len(v) > 1:
            raise ValueError("Only one skill can be selected for chat")
        return v


class ChatResponse(BaseModel):
    output: str | None
    reasoning_output: str | None
    secret_warnings: list[str] | None = None


class ChatHistoryMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    date: str
    reasoning: str | None = None


class ChatHistoryResponse(BaseModel):
    messages: list[ChatHistoryMessage]
