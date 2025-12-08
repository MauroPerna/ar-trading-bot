from typing import Optional, List, Literal, Dict, Union
from pydantic import BaseModel


class Condition(BaseModel):
    indicator: str
    operator: Literal["<", ">", "<=", ">=",
                      "==", "!=", "crossover", "crossunder"]
    value: Optional[Union[float, str]]
    lookback: int = 1


class RiskSettings(BaseModel):
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    position_sizing: Literal["fixed",
                             "percent_risk", "volatility_based"] = "fixed"
    cooldown_period: int = 0


class StrategyParamsDTO(BaseModel):
    strategy_name: str
    enabled: bool = True

    entry_rules: List[Condition]
    exit_rules: List[Condition]

    risk: RiskSettings = RiskSettings()
    metadata: Optional[Dict[str, Union[str, float, bool]]] = None


class StrategyConfigDTO(BaseModel):
    id: str
    symbol: str
    timeframe: str
    strategy_name: str
    params: StrategyParamsDTO
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    return_pct: Optional[float] = None
