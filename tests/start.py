import sys, os
current_dir = os.path.abspath('.')
sys.path.insert(0, current_dir)

from fastapi_integration import FastAPIExtended, FastApiConfig
from pydantic import PostgresDsn, RedisDsn
import uvicorn, traceback
import logging
from fastapi_integration.models import AbstractBaseUser



class MyConfig(FastApiConfig):
    debug = True
    database_url:PostgresDsn = "postgresql+asyncpg://postgres:12345@127.0.0.1:5432/test"   # Postgres Database URL
    secret_key = "2129df71b280f0768a80efcb7bf5259928f259399fd91e5b3e19991ce8806gp2"        # A Random Secret Key
    redis_url:RedisDsn = "redis://127.0.0.1:6382/0"                                        # Redis Database URL
    title = "Test"  
                                                                           # Website Title


class User(AbstractBaseUser):
    ## Add Your Desired Fields Here. You may load them in a .
    pass



settings = MyConfig

class MyApp(FastAPIExtended):
    settings = settings

    


app = MyApp(Users=User)


if __name__ == "__main__":
    try:
        
        logging.basicConfig(level=logging.INFO)
        
        uvicorn.run("start:app", host="localhost", port=8000, reload=True, workers=1)
        
    except Exception as e:
        traceback.print_exc()