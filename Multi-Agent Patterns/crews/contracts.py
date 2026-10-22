"""What each CrewAI task must return. Every model answer is validated against one of these (output_pydantic),
and the same JSON schema is handed to Claude (--json-schema), so a malformed answer never reaches the next task."""
from pydantic import BaseModel, ConfigDict, Field

SHORT = "one short sentence"   # the description is in the schema the model sees: it keeps the page readable


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Shortlist(Contract):
    listing_ids: list[str]
    note: str = Field(description=SHORT)


class Plan(Contract):
    checks: list[str]
    note: str = Field(description=SHORT)


class Choice(Contract):
    listing_id: str
    reason: str = Field(description=SHORT)


class Decision(Contract):
    action: str          # trigger | ignore
    reason: str = Field(description=SHORT)
