from pydantic import BaseModel
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
    loan_solicited  : int
    rate_proposed   : float
    evaluation      : str
    prop_status     : Optional[str] = None
    comments        : Optional[str] = None

class PropUpStatus(BaseModel):
    id              : int
    status          : str #posted, selected, funded, mortgage
    comments        : Optional[str] = None

class StatusUpdate(BaseModel):
    prop_status: str

    class Config:
        orm_mode = True