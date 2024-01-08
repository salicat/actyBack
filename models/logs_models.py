from pydantic import BaseModel
from datetime import datetime

class LogsInDbBase(BaseModel):
    action      : str
    timestamp   : datetime
    message     : str
    user_id     : str

    class Config:
        orm_mode = True