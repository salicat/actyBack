from pydantic import BaseModel
from typing import Optional


class UserIn(BaseModel):
    role            : str
    username        : str
    email           : str
    hashed_password : str
    phone           : str
    legal_address   : str
    user_city       : str
    user_department : str
    id_number       : str
    agent           : Optional [str]= None


class UserAuth(BaseModel):
    email       : str
    password    : str

class UserInfoAsk(BaseModel):
    id_number   : str

    class Config:
        orm_mode = True 

