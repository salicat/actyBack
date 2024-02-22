from pydantic import BaseModel
<<<<<<< HEAD
=======
from fastapi import UploadFile
>>>>>>> c3c48f9 (Loan Applications update)
from typing import Optional

class PropCreate(BaseModel):
    id              : Optional[int]  
    owner_id        : str
    matricula_id    : str
    address         : str
    neighbourhood   : str
    city            : str
    department      : str
<<<<<<< HEAD
    strate          : int
    area            : int
    type            : str
    tax_valuation   : int
    loan_solicited  : int
    rate_proposed   : float
    evaluation      : str
=======
    strate          : int 
    area            : int
    type            : str 
    tax_valuation   : int
    tax_valuation_file: UploadFile = None
    loan_solicited  : int
    rate_proposed   : Optional[float] = None
    evaluation      : Optional[str] = None
>>>>>>> c3c48f9 (Loan Applications update)
    prop_status     : Optional[str] = None
    comments        : Optional[str] = None

class PropUpStatus(BaseModel):
    id              : int
<<<<<<< HEAD
    status          : str #posted, selected, funded, mortgage
=======
    status          : str #available, selected, process, loaned
>>>>>>> c3c48f9 (Loan Applications update)
    comments        : Optional[str] = None

class StatusUpdate(BaseModel):
    prop_status: str

    class Config:
        orm_mode = True