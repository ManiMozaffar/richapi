# FastAPI Integration

FastAPI Integration Package simplifies FastAPI-ORM integration with pre-built models, using SQLAlchemy and Asyncpg, saving dev time.

# Installation

You can install the package using pip:
```
pip install fastapi-integration
```


# Features

The package currently includes the following features:

Pre-built models for common database tables (e.g., User, Role, etc.) The SQLAlchemyORM object, which makes it easy to perform common database operations using SQL Alchemy and asyncpg Automatic database connection management, so you don't have to worry about opening/closing connections Integrability with providing admin CRUD endpoints and interface Integrability with other packages that supports integration with SQL alchemy and phasic Command Line Support Celery Support


# Why ?

Django allows you to write acceptable code with no studding of architecture principles. It does not allow you to write good code, but it protects you from writing very bad code. In FastAPI you have ability to go both ways. With this library, as time goes by, it will protect you to not write very bad code, however you can still bypass all these protections, and write your own code if you know what you are up to.

So, if you're more of a beginner in web development and you have no good fundamental of architecture principles, then here you are.


# Why not using Tortoise ORM?
Although Tortoise ORM is a great option for ORM, this repository is not solely focused on providing an ORM solution. Instead, it aims to introduce beginners to SQL Alchemy and its concepts. Although the code would look different from the SQL Alchemy, the core concept of querying the database remains the same, which still uses SQL Alchemy syntax. Another thing is that Tortoise is newborn ORM, it is impossible to query the code below using Tortoise ORM.
This approach of introducing beginners to SQL Alchemy and providing the flexibility to use more advanced statements directly from SQL Alchemy is what makes this repository unique. It does not limit the developers to another new-born ORM and allows them to use SQL Alchemy alongside the translated ORM, all while following the best practices of Fast API.


```python
 ## My way
query = await Model1.objects.filter(
    session,
    limit=20,
    select_models=[Model2,],
    where=( 
        (Model1.name + Model2.name).icontains(random_char), 
    ),
    joins=[Model1.id == Model2.id],
    id__gte=0
)


## SQLAlchemy Way
query2 = select(
    Model1, Model2
).select_from(
    Model1
).join(
    Model2, Model1.id == Model2.id
).where(
    (Model1.name + Model2.name).icontains(random_char) &
    (Model1.id >= 0)
).limit(
    20
)
items2 = await session.execute(query2)
results = items2.all()
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
    secret_key = "2129df71b280f0768a80efcb7bf5259928f259399..."                            # A Random Secret Key
    redis_url:RedisDsn = "redis://127.0.0.1:6382/0"                                        # Redis Database URL
    title = "Fast-API Integrations"                                                        # Website Title

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


Or you can use the translated version of SQL Alchemy to Django ORM. You can check the tests folder for more information to see how ORM translation works. Here are just some examples, they're not really following the best practices.

```python
from fastapi_integration.models import AbstractModel
from fastapi_integration.db import Engine
from fastapi_integration import FastApiConfig
from sqlalchemy.orm import declarative_base


class YourConfig(FastApiConfig):
    ## Inject config here
    pass


if __name__ == "__main__":
    Base = declarative_base()
    db_engine = Engine(YourConfig())
    class Model1(AbstractModel, Base):
        __tablename__ = 'model1'
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(50), nullable=True)
        model2s = relationship("Model2", secondary=association_table, back_populates="model1s")


    class Model2(AbstractModel, Base):
        __tablename__ = 'model2'
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(50), nullable=True)
        model1s = relationship("Model1", secondary=association_table, back_populates="model2s")



## Just A Test Function
async def test():
    async with db_engine.get_pg_db_with_async() as session:
        obj1 = await Model2.objects.create(session, name="Test1")
        obj2 = await Model2.objects.create(session, name="Test2")
        obj3 = await Model2.objects.create(session, name="Test3")
        obj_manager = Model1.objects
        await obj_manager.create(session, name=f"Another Model")
        await obj_manager.add_m2m(session, model2)
        all_query = await Model2.objects.all()
        sum_query = await Model2.objects.aggregate(session, field="id", agg_func="sum")
        min_query = await Model2.objects.aggregate(session, field="id", agg_func="min")
        distinct_query = await Model2.objects.filter(session, distinct_fields=["name"], order_by="name")
        
        # Here fk__name is a field such as name, that is related to a Foreign Key relationship 
        # class such as FK, which can be done same as django using double line notation.
        double_notation = await Model2.objects.filter(session, fk__name__contains="Another Mod")

        # Update is implemented differently to django. The updating field will be injected as a parameter called data
        update = await Model2.objects.update(session, name__contains="Test", data={"name": "Test Finished"})
        

        await Model2.objects.delete(db_session=session, name="Test Finished")
        
```



# Contributing

If you would like to contribute to this package, please feel free to submit a pull request or create an issue on the GitHub repository.

# License

This package is licensed under the MIT License.
