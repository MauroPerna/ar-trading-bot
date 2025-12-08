from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd
from src.domain.strategies.dtos.config_dto import StrategyConfigDTO
from src.domain.signals.dtos.signal_dto import SignalDTO


class BaseStrategyInterpreter(ABC):
    @abstractmethod
    def interpret(
        self,
        df: pd.DataFrame,
        config: StrategyConfigDTO,
    ) -> Optional[SignalDTO]:
        """
        Devuelve UNA señal de estrategia (buy/sell/hold) o None
        si no hay nada que hacer.
        """
        ...
