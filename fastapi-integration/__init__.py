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
from db import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from common import Base


class FastAPIExtended(FastAPI):
    settings: Type[FastApiConfig] = FastApiConfig
    _routers: list = list()


    @property
    def routers(self) -> List[Tuple[routing.APIRouter, str]]:
        return self._routers


    @routers.setter
    def routers(self, value):
        setattr(self, '_routers', value)



    def __init__(self, *args, **kwargs):
        user_config = self.get_user_config()
        super().__init__(*args, **{**kwargs, **user_config})
        

        self.db_engine = Engine(user_config)
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
            async with AsyncSession(self.db_engine) as session:
                async with session.begin():
                    pass
            
            async with self.db_engine.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logging.info("Connection established")
            self.db_engine.engine.test_connection()
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
