# FastAPI Integration
FastAPI Integration Package simplifies FastAPI-ORM integration with pre-built models, using SQLAlchemy and Asyncpg, saving dev time.

# Installation
You can install the package using pip:
```
pip install fastapi-integration
```

# Usage
To use the package, simply import the relevant classes and models into your FastAPI application:

```python
from fastapi import FastAPI
from fastapi_integration.models import AbstractBaseUser ## Built-in AbstractBaseUser  Model
from fastapi_integration.config import  FastApiConfig ## Built-in Config Model
from fastapi_integration import FastAPIExtended ## Built-in app Model that has all functionality supported
from pydantic import PostgresDsn, RedisDsn
import uvicorn, traceback
import logging



class MyConfig(FastApiConfig):
    debug = True
    database_url:PostgresDsn = "postgresql+asyncpg://postgres:12345@127.0.0.1:5432/test"   # Postgres Database URL
    secret_key = "2129df71b280f0768a80efcb7bf5259928f259399fd91e5b3e19991ce8806gp2"        # A Random Secret Key
    redis_url:RedisDsn = "redis://127.0.0.1:6382/0"                                        # Redis Database URL
    title = "Test"                                                                         # Website Title


class User(AbstractBaseUser):
    ## Add Your Desired Fields Here. You may load them in a .
    pass



settings = MyConfig

class MyApp(FastAPIExtended):
    settings = settings

    


app = MyApp(Users=User)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("start:app", host="localhost", port=8000, reload=True, workers=1)
        
        

```


# Features
The package currently includes the following features:

Pre-built models for common database tables (e.g. User, Role, etc.)
The SQLAlchemyORM object, which makes it easy to perform common database operations using SQLAlchemy and asyncpg
Automatic database connection management, so you don't have to worry about opening/closing connections
Integrability with providing admin CRUD endpoints and interface


# Contributing
If you would like to contribute to this package, please feel free to submit a pull request or create an issue on the GitHub repository.

# License
This package is licensed under the MIT License.