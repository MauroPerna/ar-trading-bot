from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from src.commons.enums.signal_enums import SignalTypeEnum, SignalStrengthEnum, SignalSourceEnum


class SignalDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[str] = None
    symbol: str
    signal_source: SignalSourceEnum
    signal_type: SignalTypeEnum
    confidence: float = Field(..., ge=0.0, le=1.0)
    strength: SignalStrengthEnum
    price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
