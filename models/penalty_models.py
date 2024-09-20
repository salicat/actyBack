from pydantic import BaseModel
from datetime import date
from typing import Optional
  
class PenaltyCreate(BaseModel): 
    month           : date 
    penalty_rate    : float

class CurrentPenalty (BaseModel):
    start_date      : date #first day of the curr month
    end_date        : date #last day of the curr month
    penalty_rate    : float

class PenaltyRequest (BaseModel):
    month_year      : date

    class Config:
        from_attributes = True