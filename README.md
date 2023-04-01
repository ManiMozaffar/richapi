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
from fastapi_integration.models import User ## Built-in User Model
from fastapi_integration.config import  FastApiConfig ## Built-in Config Model
from fastapi_integration import FastAPIExtended ## Built-in app Model that has all functionality supported
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