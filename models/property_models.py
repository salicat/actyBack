from pydantic import BaseModel
from fastapi import UploadFile
from typing import Optional

class PropCreate(BaseModel):
    id              : Optional[int]  
    owner_id        : str
    matricula_id    : str
    address         : str
    neighbourhood   : str
    city            : str
    department      : str
    strate          : int 
    area            : int
    type            : str 
    tax_valuation   : int
    tax_valuation_file: UploadFile = None
    loan_solicited  : int
    rate_proposed   : Optional[float] = None
    evaluation      : Optional[str] = None
    study           : Optional[str] = None
    prop_status     : Optional[str] = None
    comments        : Optional[str] = None

class PropUpStatus(BaseModel):
    id              : int
    status          : str #available, selected, process, loaned
    study           : Optional[str] = None
    comments        : Optional[str] = None

class StatusUpdate(BaseModel):
    prop_status     : str
    study           : Optional[str] = None
    comments        : Optional[str] = None


    class Config:
        orm_mode = True