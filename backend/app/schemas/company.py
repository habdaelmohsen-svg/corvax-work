from pydantic import BaseModel

class CompanyOut(BaseModel):
    id: int
    code: str
    name_ar: str
    name_en: str
    currency: str
    logo_url: str | None = None
    primary_color: str = "#2F5BFF"
