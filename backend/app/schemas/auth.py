from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    # H17: this field carries either a username ("admin") or an email address.
    # The name stays "email" so existing clients keep working unchanged.
    email: str = Field(min_length=3, max_length=320)
    # H17: no minimum on the LOGIN field. Length policy belongs to password
    # creation, not to sign-in; enforcing it here only blocked legitimate
    # short temporary passwords while adding no security.
    password: str = Field(min_length=1, max_length=200)
    otp: str | None = Field(default=None, min_length=6, max_length=6)


class UserOut(BaseModel):
    id: int
    name_ar: str
    name_en: str
    # H17: plain string, not EmailStr. Employee accounts use internal addresses
    # such as ahmed@corvax.local, and EmailStr rejects reserved domains, which
    # made a successful sign-in fail with 500 while serialising the response.
    email: str
    username: str | None = None
    role: str
    allowed_company_ids: list[int]
    permissions_by_company: dict[int, list[str]] = {}
    branch_scope_by_company: dict[int, dict] = {}
    mfa_enabled: bool = False
    require_password_change: bool = False


class LoginOut(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    token_type: str = "bearer"
    user: UserOut



class RefreshTokenOut(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    token_type: str = "bearer"


class CompanyContextIn(BaseModel):
    company_id: int


class MfaVerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str
