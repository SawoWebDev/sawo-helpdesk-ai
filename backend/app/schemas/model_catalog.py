from pydantic import BaseModel


class ModelCatalogEntry(BaseModel):
    id: str
    provider: str
    name: str
    description: str | None
    context_length: int | None
    price_per_m_input: float | None
    price_per_m_output: float | None
    tier: str | None
    recommended: bool
