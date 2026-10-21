from datetime import date, datetime

from pydantic import BaseModel, Field


class CreateLink(BaseModel):
    url: str = Field(examples=["https://donstu.ru/abitur/"])
    alias: str | None = Field(default=None, examples=["abitur"])
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class LinkCreated(BaseModel):
    code: str
    short_url: str
    url: str
    expires_at: datetime | None
    manage_token: str = Field(description="Shown once. Needed to see stats and delete the link.")


class DayCount(BaseModel):
    day: date
    clicks: int


class NameCount(BaseModel):
    name: str
    clicks: int


class LinkStats(BaseModel):
    code: str
    url: str
    created_at: datetime
    expires_at: datetime | None
    clicks_total: int
    clicks_by_people: int
    last_30_days: list[DayCount]
    referrers: list[NameCount]
    devices: list[NameCount]
