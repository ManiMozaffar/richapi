__version__ = "0.0.2"

from fastapi import FastAPI, HTTPException, routing
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from typing import Callable, Type, Union, List, Tuple, Dict, Any
from .config import FastApiConfig
from pydantic import ValidationError
import logging
from .db import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from .auth.routers import create_auth_router
from .queries.base import QueryMixin
from sqlalchemy.orm import declarative_base





class FastAPIExtended(FastAPI):
    settings: Type[FastApiConfig] 
    _routers: list = list()
    add_auth_router: bool = True
    i = 0
    Users: QueryMixin

    
    

    @property
    def routers(self) -> List[Tuple[routing.APIRouter, str]]:
        return self._routers


    @routers.setter
    def routers(self, value):
        setattr(self, '_routers', value)



    def __init__(self, Users=None, *args, **kwargs):
        user_config = self.get_user_config()
        self.Base = declarative_base()
        super().__init__(*args, **{**kwargs, **user_config})

        self.settings = self.settings()
        self.db_engine = Engine(self.settings)
        self.add_middleware(
            CORSMiddleware,
            allow_origins=self.settings.allowed_hosts,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self.add_event_handler("startup", self.create_start_app_handler())
        self.add_event_handler("shutdown", self.create_stop_app_handler())
        self.add_exception_handler(HTTPException, self.http_error_handler)
        self.add_exception_handler(RequestValidationError, self.http422_error_handler)


        for router in self.routers:
            self.include_router(router[0], prefix=router[1])
        


        if Users:
            class Users(Users, self.Base):
                __tablename__ = "users"

            if self.add_auth_router:
                auth_router = create_auth_router(self.db_engine, self.settings, Users)
                self.include_router(auth_router, prefix="/auth")
        
        



    def get_user_config(self) -> Dict[str, Any]:
        if issubclass(self.settings, FastApiConfig):
            user_config_instance = self.settings()
            config_dict = user_config_instance.fastapi_kwargs
            return config_dict
        else:
            raise ValueError("The provided class does not inherit from FastApiConfig")



    def create_start_app_handler(self) -> Callable:
        async def start_app() -> None:
            logging.info("Connecting to  PostgreSQL")
            async with AsyncSession(self.db_engine.engine) as session:
                async with session.begin():
                    pass
            
            async with self.db_engine.engine.begin() as conn:
                await conn.run_sync(self.Base.metadata.create_all)
            logging.info("Connection established")


            self.db_engine.get_redis_db().test()
        return start_app
        # Implement your startup event handler here



    def create_stop_app_handler(self) -> Callable:
        async def stop_app() -> None:
            async with self.db_engine.engine.connect() as conn:
                await conn.close()
                await self.db_engine.engine.dispose()
        return stop_app



    async def http422_error_handler(
        _: Request,
        exc: Union[RequestValidationError, ValidationError],
    ) -> JSONResponse:
        return JSONResponse(
            {"errors": exc.errors()},
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        )

    async def http_error_handler(self, _: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"errors": [exc.detail]}, status_code=exc.status_code)
