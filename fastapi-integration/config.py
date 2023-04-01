import logging
from typing import Any, Dict, List, Tuple
from fastapi.security import OAuth2PasswordBearer
from pydantic import PostgresDsn, RedisDsn
from pydantic import BaseSettings


class FastApiConfig(BaseSettings):
    debug: bool 
    docs_url: str = "/docs"
    openapi_prefix: str = ""
    openapi_url: str = "/openapi.json"
    redoc_url: str = "/redoc"
    title: str
    version: str = "0.0.0"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 180
    oauth2_scheme:OAuth2PasswordBearer = OAuth2PasswordBearer(tokenUrl="api/auth/token")
    default_pagination: int = 20
    max_pagination: int = 100


    database_url: PostgresDsn
    redis_url: RedisDsn
    redis_max_connections: int = 100
    

    secret_key: str
    api_prefix: str = "/api"
    jwt_token_prefix: str = "Token"
    allowed_hosts: List[str] = ["*"]
    logging_level: int = logging.INFO
    loggers: Tuple[str, str] = ("uvicorn.asgi", "uvicorn.access")


    class Config:
        validate_assignment = True


    @property
    def fastapi_kwargs(self) -> Dict[str, Any]:
        return {
            "debug": self.debug,
            "docs_url": self.docs_url,
            "openapi_prefix": self.openapi_prefix,
            "openapi_url": self.openapi_url,
            "redoc_url": self.redoc_url,
            "title": self.title,
            "version": self.version,
        }