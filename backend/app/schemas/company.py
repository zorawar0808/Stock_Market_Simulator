from pydantic import BaseModel, ConfigDict


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: str
    name: str
    ticker: str
    sector: str
    description: str
    initial_price: float
    current_price: float
