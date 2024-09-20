from pydantic import BaseModel
from typing import Optional


class UserIn(BaseModel):
    role            : str
    username        : str
    email           : str
    hashed_password : Optional [str]= None
    phone           : Optional [str]= None
    legal_address   : Optional [str]= None
    user_city       : Optional [str]= None
    user_department : Optional [str]= None
    id_number       : Optional [str]= None
    agent           : Optional [str]= None
    added_by        : Optional [int]= None
    
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

class PasswordChange(BaseModel):
    password_change: str

    class Config:
        from_attributes = True 

