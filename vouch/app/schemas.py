"""Request bodies. Every model forbids unknown fields, so a client can't slip in
`role`, `approved_by`, `owner_id`, `document_id` or a replacement payload."""
from __future__ import annotations

import re
from typing import Literal

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
