from setuptools import setup, find_packages

setup(
    name="fastapi-integration",
    version="0.0.1",
    author="Mani Mozaffar",
    author_email="mani.mozaffar@gmail.com",
    description="A PyPI package for simplifying FastAPI-ORM integration",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "asyncpg",
        "sqlalchemy",
        "redis"
    ],
)
