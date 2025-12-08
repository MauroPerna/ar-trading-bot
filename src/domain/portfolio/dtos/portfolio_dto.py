from typing import Dict
from pydantic import BaseModel


class PortfolioDTO(BaseModel):
    cash_balance: float
    positions: Dict[str, float]
