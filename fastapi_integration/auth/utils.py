from datetime import datetime, timedelta
from fastapi import Depends, status, HTTPException
from pydantic import BaseModel
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import Engine
from typing import Callable
from ..config import FastApiConfig
from ..queries.base import QueryMixin
from typing import Any

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

is_not_superuser_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate administration access",
    headers={"WWW-Authenticate": "Bearer"},
)

class TokenData(BaseModel):
    user_id: int

def manager_get_current_user(db_engine: Engine, config: FastApiConfig, User: QueryMixin) -> Callable:
    async def get_current_user(
        db: AsyncSession = Depends(db_engine.get_pg_db),
        token: str = Depends(config.oauth2_scheme),
    ) -> Any:
        try:
            payload = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
            user_id = payload.get("sub")

            if user_id is None:
                raise credentials_exception

            token_data = TokenData(user_id=user_id)
        except Exception as e:
            print(e)
            raise credentials_exception

        token = db_engine.get_redis_db().get_connection().get(token)
        if token is None:
            raise credentials_exception

        user = await User.get(db_session=db, id=token_data.user_id)
        if user is None:
            raise credentials_exception

        return user

    return get_current_user

def manager_get_admin_user(db_engine: Engine, config: FastApiConfig, User: QueryMixin) -> Callable:
    async def get_admin_user(
        db: AsyncSession = Depends(db_engine.get_pg_db),
        token: str = Depends(config.oauth2_scheme),
    ) -> Any:
        try:
            payload = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
            user_id = payload.get("sub")

            if user_id is None:
                raise credentials_exception

            token_data = TokenData(user_id=user_id)
        except Exception as e:
            print(e)
            raise credentials_exception

        token = db_engine.get_redis_db().get_connection().get(token)
        if token is None:
            raise credentials_exception

        user = await User.get(db_session=db, id=token_data.user_id, is_admin=True)
        if user is None:
            raise is_not_superuser_exception

        return user

    return get_admin_user

def manager_create_access_token(db_engine: Engine, config: FastApiConfig) -> Callable:
    def create_access_token(*, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=config.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, config.secret_key, algorithm=config.algorithm)
        db_engine.get_redis_db().get_connection().set(encoded_jwt, value=1, ex=config.access_token_expire_minutes * 60)
        return encoded_jwt

    return create_access_token

def manager_delete_access_token(db_engine: Engine, config: FastApiConfig) -> Callable:
    def delete_access_token(token) -> None:
        db_engine.get_redis_db().get_connection().set(token, value=0, ex=1)

    return delete_access_token
