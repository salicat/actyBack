from pydantic import BaseModel
from datetime import date
from typing import Optional

 
class RegCreate(BaseModel):
    mortgage_id     : int 
    lender_id       : Optional [str]= None
    debtor_id       : Optional [str]= None
    date            : date
    concept         : Optional [str]= None
    amount          : int
    penalty         : Optional [int]= None
    min_payment     : Optional [int]= None
    limit_date      : Optional [date]= None
    to_main_balance : Optional [int]= None
    comprobante     : Optional [str]= None
    comment         : Optional [str]= None

class SystemReg(BaseModel):
    debtor_id       : str    
    date            : date

class RegisterCheck(BaseModel):
    lender_id   : str
    debtor_id   : str

class RegsUpDate (BaseModel):
    reg_id      : (int)
    new_status  : (str)

    class Config:
        orm_mode = True
