import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$")


class OrganizationCreate(BaseModel):
    """Payload for creating a new organization (tenant)."""

    name: str
    slug: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        if len(v) > 255:
            raise ValueError("name must be 255 characters or fewer")
        return v

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be 3–50 characters, lowercase alphanumeric and hyphens "
                "(cannot start or end with a hyphen)"
            )
        return v


class OrganizationResponse(BaseModel):
    """Public representation of an organization."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
