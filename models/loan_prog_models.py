from pydantic import BaseModel
from datetime import date
from typing import Optional

class LoanProgressInfo(BaseModel):
    id          : int
    date        : date
    property_id : int
    status      : str
    user_id     : str
    notes       : str
    updated_by  : str

class LoanProgressUpdate(BaseModel):
    date        : Optional[date] 
    status      : str
    notes       : Optional[str] = None

    class Config:
        from_attributes = True
