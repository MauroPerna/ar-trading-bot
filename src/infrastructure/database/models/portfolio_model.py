"""
Portfolio Database Model

SQLAlchemy model for portfolio.
"""

from sqlalchemy import Column, String, Float, JSON
from uuid import uuid4

from src.infrastructure.database.models.base import BaseModel


class PortfolioModel(BaseModel):
    """Portfolio database model."""
    __tablename__ = 'portfolio'

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    cash_balance = Column(Float, nullable=False)
    positions = Column(JSON, nullable=True)
