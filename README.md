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



Or you can use the translated version of SQLAlchemy to django ORM. Here is the implemented passed test.

```python
from sqlalchemy.orm import declarative_base
from sqlalchemy import (
    select
)
from fastapi_integration.db import Engine
from fastapi_integration.models import AbstractBaseUser
from tests.start import MyConfig
import random, string, unittest


def get_random_info():
    username = ''.join(random.choices(string.ascii_lowercase, k=8))    
    domain = ''.join(random.choices(string.ascii_lowercase, k=8))    
    email = username + "@" + domain + ".com"
    icontain_email = username[:-3] + "@" + domain + ".com"
    return (username, email, icontain_email)


class TestQueryMixin(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async with db_engine.get_pg_db_with_async() as session:
            self.new_email = str(random_info[1]).join(random.choices(string.ascii_lowercase, k=2))
            new_username = str(random_info[2]).join(random.choices(string.ascii_lowercase, k=2))
            self.create_user = await User.objects.create(email=random_info[1], username=random_info[0], password="testpassword", db_session=session)
            self.create_user_two = await User.objects.create(email=self.new_email, username=new_username, password="testpassword", db_session=session)
            self.order_and_limit = await User.objects.filter(db_session=session, id__gte=2, order_by="-id", limit=2)
            self.filter_icontain = await User.objects.filter(email__icontains=random_info[2][:2], db_session=session)
            self.all_query = await User.objects.all(db_session=session)
            self.values = await User.objects.filter(email__icontains=random_info[2][:2], db_session=session, values_fields=("id", "email"))
            self.startswith = await User.objects.filter(username__startswith=random_info[1][:3], db_session=session)
            self.istartswith = await User.objects.filter(username__istartswith=random_info[1][:3].upper(), db_session=session)
            self.filter_gte = await User.objects.filter(id__gte=1, db_session=session)
            self.filter_lte = await User.objects.filter(id__lte=0, db_session=session)
            self.exclude_lte = await User.objects.exclude(id__gte=1, db_session=session)
            self.multiple_exclude_lte = await User.objects.exclude(id__gte=500, email="", db_session=session)
            self.delete = await User.objects.delete(email=random_info[1], db_session=session)
            self.delete_icontians = await User.objects.delete(email__icontains=random_info[2][:2], db_session=session)

            
    async def asyncTearDown(self):                     
        async with db_engine.get_pg_db_with_async() as session:  
            await User.objects.delete(email=self.new_email, db_session=session)


        async with db_engine.engine.connect() as conn:
            await conn.close()
            await db_engine.engine.dispose()



    async def test_user_create_query(self):
        self.assertEqual(1, 1)

    async def test_user_delete_query(self):
        self.assertEqual(self.delete, 1)

    async def test_user_all_query(self):
        self.assertGreater(len(self.all_query), 1)
    

    async def test_user_field_looksup(self):
        self.assertEqual(len(self.filter_icontain), 2)    
        self.assertEqual(self.delete_icontians, 1)    
        self.assertGreater(len(self.filter_gte), 0)    
        self.assertEqual(len(self.filter_lte), 0)    
        self.assertEqual(len(self.startswith), 1)    
        self.assertEqual(len(self.istartswith), 1)
    

    async def test_user_exclude_lte(self):
        self.assertEqual(len(self.exclude_lte), 0)
    

    async def test_user_multiple_exclude_lte(self):
        self.assertGreater(len(self.multiple_exclude_lte), 0)
        

    async def test_query_order_limit(self):
        self.assertGreater(self.order_and_limit[0].id, self.order_and_limit[1].id)
        self.assertEqual(len(self.order_and_limit), 2)
    

    async def test_values(self):
        self.assertEqual(hasattr(self.values[0], 'password'), False)
    
    
    


if __name__ == "__main__":
    Base = declarative_base()
    class User(AbstractBaseUser, Base):
        __tablename__ = "users"


    random_info = get_random_info()
    db_engine = Engine(MyConfig())
    unittest.main()
```

Check out the test file for latest using case and examples of how Query Translation works



# Features
The package currently will include the following features:

Pre-built models for common database tables (e.g. User, Role, etc.)
The SQLAlchemyORM object, which makes it easy to perform common database operations using SQLAlchemy and asyncpg
Automatic database connection management, so you don't have to worry about opening/closing connections
Integrability with providing admin CRUD endpoints and interface
Integrability with other packages that supports integration with sqlalchemy and pgasync
Command Line Support
Celery Support


# Why ?
django allows you to write acceptable code with no studing of architecture principles. 
It does not allow you to write good code, but it protects you from writing very bad code. In fastapi you have ability to go both ways.
With this library, as time goes by, it will protect you to not write very bad code, however you can still bypass all these protections, and write your own code if you know what you are up to.

So if you're more of a beginner in web development and you have no good fundamental of architecture principles, then here you are. 


# Contributing
If you would like to contribute to this package, please feel free to submit a pull request or create an issue on the GitHub repository.

# License
This package is licensed under the MIT License.