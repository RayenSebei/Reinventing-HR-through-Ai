"""Request bodies. Every model forbids unknown fields, so a client can't slip in
`role`, `approved_by`, `owner_id`, `document_id` or a replacement payload."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Empty(Strict):
    """For action endpoints that take no input (approve, execute, confirm...)."""


class Comment(Strict):
    comment: str = Field(default="", max_length=500)


class Login(Strict):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class CaseCreate(Strict):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    manager_id: str | None = Field(default=None, max_length=64)


Kind = Literal["skill", "experience", "education", "project", "certification", "other"]


class Criterion(Strict):
    label: str = Field(min_length=1, max_length=200)
    kind: Kind = "skill"
    weight: int = Field(ge=0, le=100)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class CriteriaSet(Strict):
    criteria: list[Criterion] = Field(min_length=1, max_length=20)

    @field_validator("criteria")
    @classmethod
    def weights_sum_to_100(cls, v):
        total = sum(c.weight for c in v)
        if total != 100:
            raise ValueError(f"weights must add up to 100 (they add up to {total})")
        return v


class ShortlistSet(Strict):
    candidate_ids: list[str] = Field(max_length=200)

    @field_validator("candidate_ids")
    @classmethod
    def unique_candidates(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("candidate_ids must be unique")
        return values


class ProposalCreate(Strict):
    candidate_id: str = Field(max_length=64)
    kind: Literal["interview_invite", "follow_up"] = "interview_invite"
    start: str | None = Field(default=None, max_length=40, description="ISO 8601 UTC, e.g. 2030-05-01T10:00:00Z")
    duration_minutes: int = Field(default=45, ge=15, le=240)


class ProposalEdit(Strict):
    start: str | None = Field(default=None, max_length=40)
    recipient: str | None = Field(default=None, max_length=200)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=5000)
    duration_minutes: int | None = Field(default=None, ge=15, le=240)


InterviewType = Literal["screening", "technical", "behavioral", "final", "other"]
InterviewStatus = Literal["scheduled", "confirmed", "completed", "cancelled"]
TaskType = Literal[
    "review_cv", "review_assessment", "approve_communication", "send_approved_communication",
    "schedule_interview", "confirm_interview", "collect_feedback", "follow_up", "other",
]
TaskPriority = Literal["low", "normal", "high", "urgent"]
TaskStatus = Literal["open", "in_progress", "completed"]


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("timezone must be a recognized IANA time zone")
    return value


def _aware_datetime(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("must be an ISO 8601 date-time")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a time zone offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class InterviewCreate(Strict):
    case_id: str = Field(min_length=1, max_length=64)
    candidate_id: str = Field(min_length=1, max_length=64)
    interviewer_id: str = Field(min_length=1, max_length=64)
    interview_type: InterviewType
    scheduled_start: str = Field(min_length=10, max_length=40)
    duration_minutes: int = Field(ge=15, le=240)
    timezone: str = Field(min_length=1, max_length=64)
    location: str = Field(default="", max_length=300)
    preparation_notes: str = Field(default="", max_length=4000)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return _timezone(value)

    @field_validator("scheduled_start")
    @classmethod
    def valid_start(cls, value):
        return _aware_datetime(value)


class InterviewUpdate(Strict):
    interviewer_id: str | None = Field(default=None, min_length=1, max_length=64)
    interview_type: InterviewType | None = None
    scheduled_start: str | None = Field(default=None, min_length=10, max_length=40)
    duration_minutes: int | None = Field(default=None, ge=15, le=240)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=300)
    preparation_notes: str | None = Field(default=None, max_length=4000)
    feedback: str | None = Field(default=None, max_length=4000)
    status: InterviewStatus | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return _timezone(value) if value is not None else value

    @field_validator("scheduled_start")
    @classmethod
    def valid_start(cls, value):
        return _aware_datetime(value)


class FollowUpCreate(Strict):
    case_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    task_type: TaskType = "follow_up"
    candidate_id: str | None = Field(default=None, max_length=64)
    interview_id: str | None = Field(default=None, max_length=64)
    proposal_id: str | None = Field(default=None, max_length=64)
    assigned_to: str | None = Field(default=None, max_length=64)
    due_at: str | None = Field(default=None, max_length=40)
    priority: TaskPriority = "normal"

    @field_validator("due_at")
    @classmethod
    def valid_due_at(cls, value):
        return _aware_datetime(value)


class FollowUpUpdate(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    task_type: TaskType | None = None
    candidate_id: str | None = Field(default=None, max_length=64)
    interview_id: str | None = Field(default=None, max_length=64)
    proposal_id: str | None = Field(default=None, max_length=64)
    assigned_to: str | None = Field(default=None, max_length=64)
    due_at: str | None = Field(default=None, max_length=40)
    priority: TaskPriority | None = None
    status: TaskStatus | None = None

    @field_validator("due_at")
    @classmethod
    def valid_due_at(cls, value):
        return _aware_datetime(value)


class UserCreate(Strict):
    email: str = Field(min_length=3, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["recruiter", "hiring_manager", "hr_admin", "auditor"]
    password: str = Field(min_length=12, max_length=200)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if not re.fullmatch(r"[^@\s]+@[^@.\s]+(?:\.[^@.\s]+)+", value):
            raise ValueError("email must be a valid address")
        return value.lower()


class UserRoleUpdate(Strict):
    role: Literal["recruiter", "hiring_manager", "hr_admin", "auditor"]


class PolicyUpdate(Strict):
    approval_ttl_minutes: int | None = Field(default=None, ge=1, le=1440)
    review_weight_threshold: int | None = Field(default=None, ge=0, le=100)

    @field_validator("approval_ttl_minutes", "review_weight_threshold", mode="before")
    @classmethod
    def reject_null_values(cls, value):
        if value is None:
            raise ValueError("policy fields cannot be null")
        return value


# --- agenda: internal meetings and interview format -------------------------------
class MeetingCreate(Strict):
    title: str = Field(min_length=1, max_length=200)
    start: str = Field(min_length=10, max_length=40)
    duration_minutes: int = Field(ge=15, le=480)
    timezone: str = Field(min_length=1, max_length=64)
    location: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=4000)
    attendee_ids: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("start")
    @classmethod
    def valid_start(cls, value):
        return _aware_datetime(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return _timezone(value)


class MeetingUpdate(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start: str | None = Field(default=None, min_length=10, max_length=40)
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    attendee_ids: list[str] | None = Field(default=None, max_length=30)

    @field_validator("start")
    @classmethod
    def valid_start(cls, value):
        return _aware_datetime(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return _timezone(value) if value is not None else value


InterviewFormat = Literal["ai_chat", "recruiter", "senior_hr"]


class FormatDecision(Strict):
    format: InterviewFormat


class ConductedBy(Strict):
    by: Literal["ai", "human"]


class ContactConfirm(Strict):
    """HI-04/D11: the address a recruiter confirms for a candidate (validated in contacts.clean_address)."""
    email: str = Field(max_length=254)
