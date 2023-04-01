from pydantic import BaseModel


class AuthModel(BaseModel):
    token_type: str
    access_token: str



class UserOut(BaseModel):
    id: int
    username: str
    email: str