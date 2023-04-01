from queries.base import QueryMixin
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from common import Base


class User(Base, QueryMixin):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)

    api_structures = relationship("ApiStructure", back_populates="owner")
    sellers = relationship("Sellers", back_populates="owner")
    orders = relationship("EaOrder", back_populates="owner")
    payments = relationship("Payments", back_populates="owner")




    email = Column(String(50), unique=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=True)
    password = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True, default=None)
