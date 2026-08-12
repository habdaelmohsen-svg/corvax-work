from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class JournalLineIn(BaseModel):
    account_code: str
    description: str | None = None
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)
    cost_center_code: str | None = None
    branch_code: str | None = None

    @model_validator(mode="after")
    def one_side_only(self):
        if self.debit > 0 and self.credit > 0:
            raise ValueError("A journal line cannot contain both debit and credit")
        if self.debit == 0 and self.credit == 0:
            raise ValueError("A journal line must contain a debit or credit amount")
        return self


class JournalCreate(BaseModel):
    company_id: int
    entry_date: date
    reference: str = Field(min_length=1, max_length=100)
    allow_duplicate_reference: bool = False
    description: str = Field(min_length=1, max_length=500)
    cash_flow_activity: Literal["OPERATING", "INVESTING", "FINANCING"] | None = None
    cash_flow_kind: str | None = None
    lines: list[JournalLineIn] = Field(min_length=2)


class JournalLineOut(BaseModel):
    account_code: str
    account_name_ar: str
    account_name_en: str
    description: str | None
    debit: Decimal
    credit: Decimal
    cost_center_code: str | None = None
    branch_code: str | None = None


class JournalOut(BaseModel):
    id: int
    company_id: int
    number: str
    entry_date: date
    reference: str
    description: str
    status: str
    cash_flow_kind: str | None = None
    total_debit: Decimal
    total_credit: Decimal
    created_by: int
    approved_by: int | None
    posted_by: int | None
    created_at: datetime
    lines: list[JournalLineOut] = []
