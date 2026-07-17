from pydantic import BaseModel

from app.schemas import BaseORMSchema


class UserSettingsResponse(BaseORMSchema):
    agent_tool_creation: bool = False
    eval_enabled: bool = False


class UserSettingsUpdate(BaseModel):
    agent_tool_creation: bool | None = None
    eval_enabled: bool | None = None
