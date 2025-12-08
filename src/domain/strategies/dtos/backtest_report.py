from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class BacktestReport:
    """Backtest results report for a strategy run on a single asset."""

    asset: str
    strategy_name: str

    # Core metrics
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int

    # Optional extended metrics
    profit_factor: Optional[float] = None
    expectancy: Optional[float] = None
    average_trade_return: Optional[float] = None

    # Equity curve data (optional for analysis)
    equity_curve: Optional[List[float]] = None

    # Additional metadata (params, runtime, timeframe, etc)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def print_summary(self):
        print(f"Backtest Report for {self.strategy_name} on {self.asset}:")
        print(f"  Total Return: {self.total_return:.2%}")
        print(f"  Sharpe Ratio: {self.sharpe_ratio:.2f}")
        print(f"  Max Drawdown: {self.max_drawdown:.2%}")
        print(f"  Win Rate: {self.win_rate:.2%}")
        print(f"  Total Trades: {self.total_trades}")
        if self.profit_factor is not None:
            print(f"  Profit Factor: {self.profit_factor:.2f}")
        if self.expectancy is not None:
            print(f"  Expectancy: {self.expectancy:.2f}")
        if self.average_trade_return is not None:
            print(f"  Average Trade Return: {self.average_trade_return:.2%}")
