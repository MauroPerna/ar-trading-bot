from typing import List, Type, Dict, Any, Optional
import pandas as pd
from backtesting import Backtest
from src.domain.strategies.dtos.backtest_report import BacktestReport
from src.domain.strategies.services.registry import STRATEGY_REGISTRY
from src.domain.strategies.impl.base import ConfigurableStrategy


class BacktestEngine:

    def __init__(self, cash: float = 200_000, commission: float = 0.001):
        self.cash = cash
        self.commission = commission

    def run_single(
        self,
        df: pd.DataFrame,
        strategy_cls: Type[ConfigurableStrategy],
        strategy_name: str,
        asset: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> BacktestReport:
        df = df.copy()

        bt = Backtest(
            df,
            strategy_cls,
            cash=self.cash,
            commission=self.commission,
            exclusive_orders=True,
        )

        stats = bt.run(**(params or {}))

        total_return = float(stats["Return [%]"]) / 100.0
        sharpe = float(stats.get("Sharpe Ratio", 0.0))
        max_dd = float(stats.get("Max. Drawdown [%]", 0.0)) / 100.0
        win_rate = float(stats.get("Win Rate [%]", 0.0)) / 100.0
        trades = int(stats.get("# Trades", 0))

        report = BacktestReport(
            strategy_name=strategy_name,
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=trades,
            asset=asset,
            metadata={
                "asset": asset,
                "raw_stats": stats.to_dict(),
                "strategy_config": strategy_cls.get_config().model_dump(),
            },
        )

        return report

    def run_for_asset(
        self,
        df: pd.DataFrame,
        asset: str,
        strategy_names: Optional[List[str]] = None,
        strategy_params: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[BacktestReport]:
        """
        Corre backtest de varias estrategias sobre un único activo.
        """
        names = strategy_names or list(STRATEGY_REGISTRY.keys())
        params = strategy_params or {}

        reports: List[BacktestReport] = []

        for name in names:
            strategy_cls = STRATEGY_REGISTRY.get(name)
            if strategy_cls is None:
                continue

            report = self.run_single(
                df=df,
                strategy_cls=strategy_cls,
                strategy_name=name,
                asset=asset,
                params=params.get(name),
            )
            reports.append(report)

        return reports
