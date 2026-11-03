from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


class RunRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    context: str = Field(default="", max_length=12000)
    session_id: str | None = None
    models: list[str] = Field(min_length=2, max_length=4)
    judge: str = Field(min_length=3, max_length=180)
    depth: Literal["standard", "deep"] = "standard"
    demo: bool = False
    fresh: bool = False
    timezone: str = "Europe/Stockholm"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use a recognized timezone.") from error
        return value

    @field_validator("question")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a question.")
        return value.strip()

    @field_validator("models")
    @classmethod
    def distinct(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Choose different models for independent answers.")
        if any("/" not in item or len(item) > 180 for item in values):
            raise ValueError("Use OpenRouter model IDs, such as provider/model.")
        return values


class Point(BaseModel):
    claim: str = Field(description="One concise finding or disagreement.")
    detail: str = Field(description="Explain evidence, assumptions, or different positions.")
    source_ids: list[str] = Field(default_factory=list)


class Comparison(BaseModel):
    answer: str = Field(description="Helpful direct answer in Markdown, with [source](URL) citations.")
    agreements: list[Point] = Field(description="Up to 5 supported agreements, not votes for truth.")
    disagreements: list[Point] = Field(description="Up to 5 material conflicts; preserve useful minority views.")
    next_steps: list[str] = Field(description="Up to 4 practical next steps.")
    limitations: list[str] = Field(description="Missing evidence, failed researchers, unresolved facts.")
