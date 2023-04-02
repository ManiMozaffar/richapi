from pydantic import BaseModel
from sqlalchemy.orm import relationship, declarative_base


class Status(BaseModel):
    message: str
    status: str