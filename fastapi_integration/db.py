from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import redis
import logging
from .config import FastApiConfig
from contextlib import asynccontextmanager



class RedisDb:
    def __init__(self, setting:FastApiConfig) -> None:
        self.redis_pool = redis.ConnectionPool(
            host=setting.redis_url.host,
            port=setting.redis_url.port,
            db=int(setting.redis_url.path[1:]),
            username=setting.redis_url.user,
            password=setting.redis_url.password,
            max_connections=setting.redis_max_connections,
        )
        
    
    def test(self):
        logging.info("Connecting to Redis")
        redis_conn = redis.Redis(connection_pool=self.redis_pool)
        redis_conn.set('test', 'test', ex=1)
        logging.info("Connection established")
    

    def get_connection(self) -> redis.Redis:
        return redis.Redis(connection_pool=self.redis_pool)



class Engine:
    def __init__(self, setting:FastApiConfig) -> None:
        self.setting = setting
        self.engine = create_async_engine(
            setting.database_url,
            future=True,
            echo=False,
        )

        self.async_session_factory = sessionmaker(
            self.engine, autoflush=False, expire_on_commit=False, class_=AsyncSession
        )


    async def get_pg_db(self) -> AsyncGenerator:
        self.async_session_factory = sessionmaker(
            self.engine, autoflush=False, expire_on_commit=False, class_=AsyncSession
        )
        async with self.async_session_factory() as session:
            logging.info(f"ASYNC Pool: {self.engine.pool.status()}")
            yield session
    

    
    async def create_database(self, Base):
        logging.info("Connecting to  PostgreSQL")
        async with AsyncSession(self.engine) as session:
            async with session.begin():
                pass
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logging.info("Connection established")



    @asynccontextmanager
    async def get_pg_db_with_async(self) -> AsyncSession:
        async with self.async_session_factory() as session:
            logging.info(f"ASYNC Pool: {self.engine.pool.status()}")
            yield session

         
    def get_redis_db (self) -> RedisDb:
        return RedisDb(setting=self.setting)
    


def create_engine(settings:FastApiConfig) -> Engine:
    return Engine(settings)