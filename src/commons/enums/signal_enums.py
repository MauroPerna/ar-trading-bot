from enum import Enum


class SignalTypeEnum(str, Enum):
    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"
    HOLD = "hold"
    ALERT = "alert"


class SignalStrengthEnum(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    EXTREME = "extreme"


class SignalSourceEnum(str, Enum):
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    RISK = "risk"
    STRUCTURE = "structure"
    TREND = "trend"
