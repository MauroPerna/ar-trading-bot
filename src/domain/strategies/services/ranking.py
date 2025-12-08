
from typing import List
from ..dtos.backtest_report import BacktestReport


def rank_reports(reports: List[BacktestReport]) -> List[BacktestReport]:
    """
    Orden simple:
      1) mayor Sharpe
      2) si empata, menor drawdown
      3) si empata, mayor total_return
    """
    return sorted(
        reports,
        key=lambda r: (-r.sharpe_ratio, r.max_drawdown, -r.total_return),
    )
