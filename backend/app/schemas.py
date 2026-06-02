"""Shared schema utilities — validators, base classes, and helpers.

This module provides reusable components for Pydantic schemas across
all domain modules.
"""

from pydantic import BaseModel, field_validator


def validate_github_url(v: str) -> str:
    """Validate that a URL contains github.com."""
    if "github.com" not in v:
        raise ValueError("Must be a valid GitHub URL")
    return v.strip()


class GithubUrlValidatorMixin:
    """Mixin that adds github_url validation to a Pydantic model."""

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        return validate_github_url(v)


class BaseORMSchema(BaseModel):
    """Base schema for response models that map from SQLAlchemy ORM objects.

    Enables Pydantic's from_attributes mode so that ORM objects can be
    converted to schemas without manual field mapping.
    """

    model_config = {"from_attributes": True}
