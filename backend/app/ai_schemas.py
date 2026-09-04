"""Schemas shared by OpenAI Structured Outputs and the persistence boundary."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
TextList = Annotated[list[Text], Field(max_length=100)]
Priority = Literal["LOW", "MEDIUM", "HIGH"]
Category = Literal["HEALTH", "NUTRITION", "EMOTION", "FAMILY", "HOUSING", "SOCIAL"]


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StatusOutput(OutputModel):
    health: TextList
    nutrition: TextList
    emotion: TextList
    family: TextList
    housing: TextList
    social: TextList


class NoteOutput(OutputModel):
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    main_contents: TextList
    client_status: StatusOutput


class ChangeOutput(OutputModel):
    category: Category
    change: Literal["IMPROVED", "UNCHANGED", "WORSENED", "UNKNOWN"]
    previous: Text | None
    current: Text | None
    description: Text


class RiskOutput(OutputModel):
    type: Literal[
        "HEALTH",
        "NUTRITION",
        "EMOTION",
        "ISOLATION",
        "ABUSE",
        "HOUSING",
        "ECONOMIC",
        "SAFETY",
        "OTHER",
    ]
    severity: Priority
    description: Text
    evidence: Text | None


class ActionOutput(OutputModel):
    action_type: Literal[
        "FOLLOW_UP_CALL",
        "HOME_VISIT",
        "CONTACT_FAMILY",
        "CONTACT_SUPPORT_WORKER",
        "RESOURCE_REFERRAL",
        "CASE_REVIEW",
        "CHECK_HEALTH",
        "CHECK_NUTRITION",
        "OTHER",
    ]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Text | None
    priority: Priority
    reason: Text
    due_in_days: Annotated[int, Field(ge=0, le=365)] | None


class FollowUpOutput(OutputModel):
    important_changes: list[ChangeOutput] = Field(max_length=100)
    risk_flags: list[RiskOutput] = Field(max_length=100)
    unresolved_issues: TextList
    recommended_actions: list[ActionOutput] = Field(max_length=100)
