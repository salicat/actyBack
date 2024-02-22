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
    
class UserInfoUpdate(BaseModel):
    legal_address   :Optional [str]= None,
    user_city       :Optional [str]= None,
    user_department :Optional [str]= None,
    id_number       :Optional [str]= None,
    tax_id          :Optional [str]= None,
    bank_name       :Optional [str]= None,
    bank_account    :Optional [str]= None,
    account_number  :Optional [str]= None,

class UserAuth(BaseModel):
    email       : str
    password    : str

class UserInfoAsk(BaseModel):
    id_number   : str

    class Config:
        orm_mode = True 

