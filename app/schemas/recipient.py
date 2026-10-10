import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RecipientInput(BaseModel):
    """Raw recipient entry submitted in bulk requests."""
    name: str = Field(..., description="Full name of recipient", min_length=1, max_length=255)
    email: str = Field(..., description="Email address of recipient", min_length=3, max_length=255)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Recipient name cannot be blank or only whitespace.")
        return trimmed

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()

    def is_valid_email(self) -> bool:
        """Returns True if the email syntax is valid."""
        return bool(EMAIL_REGEX.match(self.email))


class RecipientSummary(BaseModel):
    """Output representation for an individual recipient result."""
    row_index: int
    name: str
    email: str
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
