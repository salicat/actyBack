from pydantic import BaseModel
from fastapi import UploadFile
from typing import Optional

class PropCreate(BaseModel):
    id              : Optional[int]  
    owner_id        : str
    matricula_id    : str
    address         : Optional[str] = None
    neighbourhood   : Optional[str] = None
    city            : Optional[str] = None
    department      : Optional[str] = None
    strate          : Optional[int] = None
    area            : Optional[int] = None
    type            : Optional[str] = None
    tax_valuation   : Optional[int] = None
    tax_valuation_file: UploadFile = None
    loan_solicited  : Optional[int] = None
    rate_proposed   : Optional[float] = None
    evaluation      : Optional[str] = None
    study           : Optional[str] = None
    prop_status     : Optional[str] = None
    comments        : Optional[str] = None
    youtube_link    : Optional[str] = None

class PropUpStatus(BaseModel):
    id              : int
    status          : str #available, selected, process, loaned
    study           : Optional[str] = None
    comments        : Optional[str] = None

class StatusUpdate(BaseModel):
    prop_status     : str
    study           : Optional[str] = None
    comments        : Optional[str] = None

class PropertyUpdate(BaseModel):
    address         : Optional[str] = None
    neighbourhood   : Optional[str] = None
    city            : Optional[str] = None
    department      : Optional[str] = None
    strate          : Optional[int] = None
    area            : Optional[int] = None
    type            : Optional[str] = None
    tax_valuation   : Optional[int] = None
    loan_solicited  : Optional[int] = None

    class Config:
        from_attributes = True