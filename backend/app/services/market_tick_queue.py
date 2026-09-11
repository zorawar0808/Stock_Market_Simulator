from pydantic import BaseModel


MARKET_TICK_TOPIC = "esummit-market-tick"
TICK_DELAY_SECONDS = 4


class MarketTickPayload(BaseModel):
    expected_sequence: int
    run_id: str
