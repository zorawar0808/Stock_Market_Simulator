import uuid

from pydantic import BaseModel, Field


class TeamCreateRequest(BaseModel):
    team_name: str = Field(min_length=1, max_length=120)
    max_members: int = Field(default=3, ge=1, le=20)
    starting_capital: float = Field(default=10000, gt=0)


class TeamOut(BaseModel):
    team_id: uuid.UUID
    team_name: str
    invitation_code: str
    max_members: int
    starting_capital: float
    status: str
    member_count: int

    model_config = {"from_attributes": True}


class PortfolioOut(BaseModel):
    team_id: uuid.UUID
    cash: float
    portfolio_value: float
    net_worth: float
    return_percent: float

    model_config = {"from_attributes": True}


class HoldingOut(BaseModel):
    company_id: uuid.UUID
    ticker: str
    company_name: str
    shares: float
    average_purchase_price: float
    current_price: float
    holding_value: float
    unrealized_pl: float
    unrealized_pl_percent: float
