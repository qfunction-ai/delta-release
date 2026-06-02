import os

from pydantic import BaseModel, computed_field

from app.schemas import BaseORMSchema


class UserSettingsResponse(BaseORMSchema):
    agent_tool_creation: bool = False
    eval_enabled: bool = False
    web_search_enabled: bool = False
    docs_fetch_enabled: bool = False

    @computed_field
    @property
    def exa_key_configured(self) -> bool:
        """Whether EXA_API_KEY is set in the environment (required for web_search)."""
        return bool(os.environ.get("EXA_API_KEY"))


class UserSettingsUpdate(BaseModel):
    agent_tool_creation: bool | None = None
    eval_enabled: bool | None = None
    web_search_enabled: bool | None = None
    docs_fetch_enabled: bool | None = None
