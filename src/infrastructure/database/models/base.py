# src/infrastructure/database/models/base.py
"""
Base Database Model

Base class for all database models.
"""

from datetime import datetime

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, DateTime

Base = declarative_base()


class BaseModel(Base):
    """Base model with common fields."""
    __abstract__ = True

    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )
