from fastapi import Depends, HTTPException, APIRouter, Header
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from .utils import manager_create_access_token, manager_get_current_user, manager_delete_access_token
from fastapi.security import OAuth2PasswordRequestForm
from .security import pwd_context
from .schemas import AuthModel, UserOut
from ..common import Status
from ..db import Engine
from ..config import FastApiConfig
from ..queries.base import QueryMixin


def create_auth_router(db_engine: Engine, config: FastApiConfig, User: QueryMixin) -> APIRouter:
    auth_router = APIRouter()
    get_current_user = manager_get_current_user(db_engine, config, User)

    @auth_router.post("/token", response_model=AuthModel)
    async def login_for_access_token(
        form_data: OAuth2PasswordRequestForm = Depends(),
        db_session: AsyncSession = Depends(db_engine.get_pg_db),
    ):
        user = await User.get(db_session=db_session, email=form_data.username)
        if not (user and pwd_context.verify(form_data.password, user.password)):
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Incorrect email or password",
            )

        create_access_token = manager_create_access_token(db_session, config, User)
        access_token = create_access_token(data={"sub": user.id})
        return {"access_token": access_token, "token_type": "bearer"}

    @auth_router.get("/users/me", response_model=UserOut)
    async def read_users_me(current_user: User = Depends(get_current_user)):
        return current_user

    @auth_router.delete("/logout", response_model=Status)
    async def logout(current_user: User = Depends(get_current_user), authorization: str = Header(None)):
        token_parts = authorization.split("Bearer ")
        if len(token_parts) != 2:
            return Status(message="Already logged out", status="ok")
        else:
            delete_access_token = manager_delete_access_token(db_engine, config)
            delete_access_token(token_parts[1])
            return Status(message="Logged Out", status="ok")

    return auth_router
