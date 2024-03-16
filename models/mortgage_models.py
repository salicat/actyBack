from pydantic   import BaseModel
from datetime   import date
from typing     import Optional

class MortgageCreate(BaseModel):
    lender_id           : Optional[str] = None 
    debtor_id           : str
    agent_id            : Optional[str] = None
    matricula_id        : str
    start_date          : Optional[date] = None
    initial_balance     : int
    interest_rate       : float
    current_balance     : Optional[int] = None
    last_update         : Optional[date] = None
    mortgage_state      : Optional[str] = None
    monthly_payment     : Optional[int] = None
    mortgage_status     : Optional[str] = None
    

class MortgageUpdate(BaseModel):
    amount          : Optional[int]
    date_signed     : Optional[date]

    class Config:
        orm_mode = True  
    