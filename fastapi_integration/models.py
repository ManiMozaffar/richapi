from .queries.base import QueryMixin
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime


class AbstractBaseUser(QueryMixin):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(50), unique=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=True)
    password = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True, default=None)



class AbstractOAuth2User(QueryMixin):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    oauth_name = Column(String(100), unique=True, index=True)
    access_token = Column(String(200), unique=True, index=True)
    expires_at = Column(DateTime, nullable=True, default=None)
    refresh_token = Column(String(200), unique=True, index=True)
    account_id = Column(String(30), unique=True, index=True)
    account_email = Column(String(200), unique=True, index=True)