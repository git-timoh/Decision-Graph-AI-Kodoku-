"""SQLAlchemy declarative base. Concrete models land in M2."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""
