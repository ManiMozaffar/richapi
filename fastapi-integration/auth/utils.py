# token.py
from datetime import datetime, timedelta
from fastapi import Depends, status, HTTPException
from pydantic import BaseModel
import jwt
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from models import User
from db import Engine
from typing import Callable
from config import FastApiConfig



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



def manager_get_current_user(db_session:Engine, config:FastApiConfig) -> Callable:
    async def get_current_user(
        db: AsyncSession = Depends(db_session.async_session_factory),
        token: str = Depends(config.oauth2_scheme)
    ) -> User:
        try:
            payload = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
            user_id = payload.get("sub")
                    
            if user_id is None:
                raise credentials_exception
            token_data = TokenData(user_id=user_id)
        except Exception as e:
            print(e)
            raise credentials_exception
        
        token = db_session.get_redis_db().get_connection().get(token)
        if token is None:
            raise credentials_exception

        user = await User.get(db_session=db, id=token_data.user_id)
        if user is None:
            raise credentials_exception
        return user


    return get_current_user




def manager_get_admin_user(db_session:Engine, config:FastApiConfig) -> Callable:
    async def get_admin_user(
        db: AsyncSession = Depends(db_session.async_session_factory),
        token: str = Depends(config.oauth2_scheme)
    ) -> User:

        try:
            payload = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
            user_id = payload.get("sub")
                    
            if user_id is None:
                raise credentials_exception
            token_data = TokenData(user_id=user_id)
        except Exception as e:
            print(e)
            raise credentials_exception


        token = db_session.get_redis_db().get_connection().get(token)
        if token is None:
            raise credentials_exception
        
        user = await User.get(db_session=db, id=token_data.user_id, is_admin=True)
        if user is None:
            raise is_not_superuser_exception
        
        return user
    
    return get_admin_user





def manager_create_access_token(db_session:Engine, config:FastApiConfig) -> Callable:
    def create_access_token(*, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=config.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, config.secret_key, algorithm=config.algorithm)
        db_session.get_redis_db().get_connection().set(encoded_jwt, value=1, ex=config.access_token_expire_minutes*60)
        return encoded_jwt
    
    return create_access_token



def manager_delete_access_token(db_session:Engine, config:FastApiConfig) -> Callable:
    def delete_access_token(token) -> str:
        db_session.get_redis_db().get_connection().set(token, value=0, ex=1)

    return delete_access_token