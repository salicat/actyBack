from pydantic import BaseModel
from datetime import datetime

class HelpTicket(BaseModel):
    mensaje     : str
    motivo      : str
            
    class Config:
        from_attributes = True